"""Transformers: each takes a frame and returns a ``TransformOutcome``.

A ``TransformOutcome`` holds the new frame and the values the
transformer corrected; most transformers correct nothing.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import pandas as pd

from survey_etl.layout import LAYOUT, DataStatus, SurveyLayout
from survey_etl.transform.frames import NULLABLE_INTEGER
from survey_etl.transform.reports import CorrectedValue, CorrectionReason

__all__ = [
    "TRANSFORMERS",
    "TransformOutcome",
    "Transformer",
    "add_age_columns",
    "correct_usage_without_awareness",
    "format_interview_dates",
    "tag_as_new",
]


@dataclass(frozen=True, slots=True)
class TransformOutcome:
    """A frame after one or more transformers, with their corrections.

    Attributes:
        frame: Rows after the transformation.
        corrections: Values changed, in batch order.
    """

    frame: pd.DataFrame
    corrections: tuple[CorrectedValue, ...] = ()


type Transformer = Callable[[pd.DataFrame], TransformOutcome]


def _corrections(
    frame: pd.DataFrame, column: str, layout: SurveyLayout
) -> list[CorrectedValue]:
    """Record each row of a frame slice whose column is set to 0."""
    respondent_ids = frame[layout.columns.respondent_id].tolist()
    received_values = frame[column].tolist()

    return [
        CorrectedValue(
            int(row_number),
            int(respondent_id),
            column,
            int(received),
            0,
            CorrectionReason.USAGE_WITHOUT_AWARENESS,
        )
        for row_number, respondent_id, received in zip(
            frame.index.tolist(), respondent_ids, received_values, strict=True
        )
    ]


def correct_usage_without_awareness(
    frame: pd.DataFrame, layout: SurveyLayout = LAYOUT
) -> TransformOutcome:
    """Set usage to 0 where the respondent is not aware of the brand.

    Awareness is asked first: a respondent who is not aware of a brand,
    or did not answer the awareness question, cannot use it.

    Args:
        frame: Rows to correct.
        layout: Survey layout declaring the brands.

    Returns:
        The corrected rows and one correction per changed value.
    """
    corrected = frame.copy()
    corrections: list[CorrectedValue] = []

    for brand in layout.brands:
        awareness = layout.awareness_column(brand)
        usage = layout.usage_column(brand)
        is_used = frame[usage].eq(1).fillna(value=False)
        is_aware = frame[awareness].eq(1).fillna(value=False)
        is_inconsistent = is_used & ~is_aware
        corrected.loc[is_inconsistent, usage] = 0
        corrections += _corrections(frame.loc[is_inconsistent], usage, layout)

    ordered_corrections = sorted(
        corrections, key=lambda correction: correction.row_number
    )

    return TransformOutcome(corrected, tuple(ordered_corrections))


def add_age_columns(
    frame: pd.DataFrame,
    layout: SurveyLayout = LAYOUT,
    integer_dtype: pd.Int64Dtype = NULLABLE_INTEGER,
) -> TransformOutcome:
    """Add the age in the interview year and its age category.

    The survey records only the year of birth, so the age is the
    interview year minus the birth year: it can exceed the exact age by
    one when the birthday falls after the interview.

    Args:
        frame: Rows with interview dates still as ``datetime.date``.
        layout: Survey layout declaring the columns and age bands.
        integer_dtype: Dtype of the age column.

    Returns:
        The rows with the age and age category columns added.
    """
    columns = layout.columns
    interview_years = pd.to_datetime(frame[columns.interview_date]).dt.year
    ages = (interview_years - frame[columns.birth_year]).astype(integer_dtype)
    categories = ages.map(layout.age_category_label).astype(object)

    return TransformOutcome(
        frame.assign(**{columns.age: ages, columns.age_category: categories})
    )


def format_interview_dates(
    frame: pd.DataFrame, layout: SurveyLayout = LAYOUT
) -> TransformOutcome:
    """Convert interview dates to the storage text format.

    Args:
        frame: Rows with interview dates as ``datetime.date``.
        layout: Survey layout declaring the column and the format.

    Returns:
        The rows with interview dates as text, e.g. ``"20260915"``.
    """
    column = layout.columns.interview_date
    dates = pd.to_datetime(frame[column])
    formatted_dates = dates.dt.strftime(layout.storage_date_format)

    return TransformOutcome(frame.assign(**{column: formatted_dates}))


def tag_as_new(
    frame: pd.DataFrame, layout: SurveyLayout = LAYOUT
) -> TransformOutcome:
    """Mark every row as new, i.e. not yet included in summaries.

    Args:
        frame: Rows to tag.
        layout: Survey layout declaring the status column.

    Returns:
        The rows with the status column set to ``new``.
    """
    status = {layout.columns.data_status: DataStatus.NEW.value}

    return TransformOutcome(frame.assign(**status))


# Order matters: ages need the interview dates before they become text.
TRANSFORMERS: Final[tuple[Transformer, ...]] = (
    correct_usage_without_awareness,
    add_age_columns,
    format_interview_dates,
    tag_as_new,
)
