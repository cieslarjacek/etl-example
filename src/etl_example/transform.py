"""Cleaning and transformation of validated rows with pandas.

Every function is pure: it takes a DataFrame and returns a new one.
The frame index holds each row's 1-based position in the batch, so
issues can point back to the uploaded row.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd

from etl_example.reports import IssueReason, RowIssue, in_batch_order
from etl_example.survey import LAYOUT, DataStatus, SurveyLayout
from etl_example.validation import ValidRow

__all__ = [
    "StepResult",
    "TransformResult",
    "add_age_columns",
    "build_frame",
    "correct_usage_without_awareness",
    "drop_rows_without_answers",
    "format_interview_dates",
    "frame_to_records",
    "tag_as_new",
    "transform_rows",
]

# pandas nullable integer dtype: keeps unanswered questions as <NA>.
NULLABLE_INTEGER: Final = pd.Int64Dtype()


@dataclass(frozen=True, slots=True)
class StepResult:
    """Output of a cleaning step.

    Attributes:
        frame: Rows after the step.
        issues: Rows dropped or values corrected by the step.
    """

    frame: pd.DataFrame
    issues: tuple[RowIssue, ...]


@dataclass(frozen=True, slots=True)
class TransformResult:
    """Output of the whole transformation.

    Attributes:
        frame: Rows ready to be stored.
        dropped_rows: Rows removed during cleaning.
        corrected_rows: Values changed during cleaning.
    """

    frame: pd.DataFrame
    dropped_rows: tuple[RowIssue, ...]
    corrected_rows: tuple[RowIssue, ...]


def build_frame(
    rows: Sequence[ValidRow],
    layout: SurveyLayout = LAYOUT,
    integer_dtype: pd.Int64Dtype = NULLABLE_INTEGER,
) -> pd.DataFrame:
    """Build a frame of valid rows, indexed by row number.

    Args:
        rows: Rows that passed validation.
        layout: Survey layout declaring the columns.
        integer_dtype: Dtype of the integer columns.

    Returns:
        One frame row per valid row, with nullable integer columns.
    """
    frame = pd.DataFrame.from_records(
        [dict(row.values) for row in rows],
        index=[row.row_number for row in rows],
        columns=list(layout.input_columns),
    )
    integer_columns = [
        column
        for column in layout.input_columns
        if column not in layout.text_input_columns
    ]
    return frame.astype(dict.fromkeys(integer_columns, integer_dtype))


def _issues_for(
    respondent_ids: pd.Series[int], reason: IssueReason, detail: str
) -> list[RowIssue]:
    """Build one issue per row of a respondent ID series."""
    return [
        RowIssue(int(row_number), int(respondent_id), reason, detail)
        for row_number, respondent_id in zip(
            respondent_ids.index.tolist(), respondent_ids.tolist(), strict=True
        )
    ]


def drop_rows_without_answers(
    frame: pd.DataFrame, layout: SurveyLayout = LAYOUT
) -> StepResult:
    """Drop rows where every awareness and usage answer is missing.

    Args:
        frame: Rows to clean.
        layout: Survey layout declaring the answer columns.

    Returns:
        The answered rows and one issue per dropped row.
    """
    answers = frame[list(layout.answer_columns)]
    is_unanswered = answers.isna().all(axis="columns")
    issues = _issues_for(
        frame.loc[is_unanswered, layout.respondent_id],
        IssueReason.NO_ANSWERS,
        "all awareness and usage answers are missing",
    )
    return StepResult(frame.loc[~is_unanswered], tuple(issues))


def correct_usage_without_awareness(
    frame: pd.DataFrame, layout: SurveyLayout = LAYOUT
) -> StepResult:
    """Set usage to 0 where the respondent is not aware of the brand.

    Awareness is asked first: a respondent who is not aware of a brand,
    or did not answer the awareness question, cannot use it.

    Args:
        frame: Rows to clean.
        layout: Survey layout declaring the brands.

    Returns:
        The corrected rows and one issue per corrected value.
    """
    corrected = frame.copy()
    issues: list[RowIssue] = []
    for brand in layout.brands:
        awareness = layout.awareness_column(brand)
        usage = layout.usage_column(brand)
        is_inconsistent = frame[usage].eq(1).fillna(value=False) & frame[
            awareness
        ].ne(1).fillna(value=True)
        corrected.loc[is_inconsistent, usage] = 0
        issues += _issues_for(
            frame.loc[is_inconsistent, layout.respondent_id],
            IssueReason.USAGE_WITHOUT_AWARENESS,
            f"{usage} set to 0 because {awareness} is not 1",
        )
    return StepResult(corrected, in_batch_order(issues))


def add_age_columns(
    frame: pd.DataFrame,
    layout: SurveyLayout = LAYOUT,
    integer_dtype: pd.Int64Dtype = NULLABLE_INTEGER,
) -> pd.DataFrame:
    """Add the age in the interview year and its age category.

    The survey records only the year of birth, so the age is the
    interview year minus the birth year: it can exceed the exact age
    by one when the birthday falls after the interview.

    Args:
        frame: Rows with interview dates still as ``datetime.date``.
        layout: Survey layout declaring the columns and age bands.
        integer_dtype: Dtype of the age column.

    Returns:
        The rows with the age and age category columns added.
    """
    interview_years = pd.to_datetime(frame[layout.interview_date]).dt.year
    ages = (interview_years - frame[layout.birth_year]).astype(integer_dtype)
    categories = ages.map(layout.age_category_label).astype(object)
    return frame.assign(**{layout.age: ages, layout.age_category: categories})


def format_interview_dates(
    frame: pd.DataFrame, layout: SurveyLayout = LAYOUT
) -> pd.DataFrame:
    """Convert interview dates to the storage text format.

    Args:
        frame: Rows with interview dates as ``datetime.date``.
        layout: Survey layout declaring the column and the format.

    Returns:
        The rows with interview dates as text, e.g. ``"20260915"``.
    """
    dates = pd.to_datetime(frame[layout.interview_date])
    formatted_dates = dates.dt.strftime(layout.storage_date_format)
    return frame.assign(**{layout.interview_date: formatted_dates})


def tag_as_new(
    frame: pd.DataFrame, layout: SurveyLayout = LAYOUT
) -> pd.DataFrame:
    """Mark every row as new, i.e. not yet included in summaries.

    Args:
        frame: Rows to tag.
        layout: Survey layout declaring the status column.

    Returns:
        The rows with the status column set to ``new``.
    """
    return frame.assign(**{layout.data_status: DataStatus.NEW.value})


def transform_rows(
    rows: Sequence[ValidRow], layout: SurveyLayout = LAYOUT
) -> TransformResult:
    """Clean valid rows and derive the stored columns.

    Args:
        rows: Rows that passed validation.
        layout: Survey layout declaring columns, brands and age bands.

    Returns:
        Rows ready to be stored, with the dropped and corrected rows.
    """
    answered = drop_rows_without_answers(build_frame(rows, layout), layout)
    consistent = correct_usage_without_awareness(answered.frame, layout)
    with_ages = add_age_columns(consistent.frame, layout)
    formatted = format_interview_dates(with_ages, layout)
    return TransformResult(
        tag_as_new(formatted, layout), answered.issues, consistent.issues
    )


def frame_to_records(frame: pd.DataFrame) -> tuple[dict[str, object], ...]:
    """Convert a frame to records of plain Python values.

    Database drivers cannot bind pandas' missing-value marker, so
    missing values become None.

    Args:
        frame: Rows to convert.

    Returns:
        One dictionary per row, keyed by column name.
    """
    plain = frame.astype(object).where(frame.notna(), None)
    return tuple(
        {str(column): value for column, value in record.items()}
        for record in plain.to_dict(orient="records")
    )
