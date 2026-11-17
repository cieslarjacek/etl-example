"""Row checks and the row values they pass along.

A check receives a row and the rows accepted so far, and returns the
row, possibly with converted values, or a ``Rejection``.
"""

import datetime
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Annotated, Any, Final

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
)

from etl_example.survey import LAYOUT, SurveyLayout
from etl_example.validate.reports import IssueReason

__all__ = [
    "ROW_CHECKS",
    "ROW_MODEL",
    "CheckedRow",
    "Rejection",
    "RowCheck",
    "ValidRow",
    "build_row_model",
    "build_stored_id_check",
    "check_has_answers",
    "check_minimum_age",
    "check_unique_id",
    "check_values",
]

# A 0-1 survey answer. None means the question was not answered.
_Dummy = Annotated[int | None, Field(ge=0, le=1)]


class _StrictRow(BaseModel):
    """Base of generated row models: strict types, no unknown keys."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _date_parser(date_format: str) -> Callable[[object], object]:
    """Return a pydantic pre-validator parsing dates in a format.

    Args:
        date_format: ``strptime`` format of the incoming dates.

    Returns:
        A function turning matching text into a ``datetime.date``.
    """

    def parse(value: object) -> object:
        if not isinstance(value, str):
            return value  # pydantic then reports the wrong type
        return datetime.datetime.strptime(value, date_format).date()

    return parse


def build_row_model(layout: SurveyLayout = LAYOUT) -> type[BaseModel]:
    """Build the pydantic model of one incoming survey row.

    Args:
        layout: Survey layout declaring the columns and brands.

    Returns:
        A model class with one required field per input column.
    """
    interview_date = Annotated[
        datetime.date, BeforeValidator(_date_parser(layout.input_date_format))
    ]
    fields: dict[str, Any] = {
        layout.columns.respondent_id: (Annotated[int, Field(gt=0)], ...),
        layout.columns.interview_date: (interview_date, ...),
        layout.columns.wave: (Annotated[int, Field(ge=1)], ...),
        layout.columns.birth_year: (int, ...),
    }
    fields |= dict.fromkeys(layout.answer_columns, (_Dummy, ...))

    return create_model("RespondentRow", __base__=_StrictRow, **fields)


ROW_MODEL: Final = build_row_model()


@dataclass(frozen=True, slots=True)
class ValidRow:
    """A row that passed every check.

    Attributes:
        row_number: 1-based position of the row in the batch.
        respondent_id: Respondent identifier.
        values: Validated values keyed by column name.
    """

    row_number: int
    respondent_id: int
    values: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class CheckedRow:
    """A row on its way through the checks.

    Attributes:
        row_number: 1-based position of the row in the batch.
        received_values: The row's values as received.
        values: The values so far; typed after ``check_values``.
    """

    row_number: int
    received_values: Mapping[str, object]
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Rejection:
    """Why a check rejected a row.

    Attributes:
        reason: Category of the problem.
        details: Human-readable description.
    """

    reason: IssueReason
    details: str


type RowCheck = Callable[
    [CheckedRow, Sequence[ValidRow]], CheckedRow | Rejection
]


def _describe_errors(error: ValidationError) -> str:
    """Join pydantic error messages into one line per field."""
    return "; ".join(
        f"{'.'.join(map(str, details['loc']))}: {details['msg']}"
        for details in error.errors()
    )


def check_values(
    row: CheckedRow,
    valid_rows: Sequence[ValidRow],
    row_model: type[BaseModel] = ROW_MODEL,
) -> CheckedRow | Rejection:
    """Check types and ranges.

    Important: The interview date is parsed into a ``datetime.date``.
    The other values are returned as received.

    Args:
        row: Row to check, with its values as received.
        valid_rows: Rows accepted so far (not used by this check).
        row_model: Pydantic model of one row.

    Returns:
        The row with typed values or the rejection.
    """
    try:
        # Strict mode accepts only a real dict, not a read-only mapping.
        model = row_model.model_validate(dict(row.received_values))
    except ValidationError as error:
        return Rejection(IssueReason.INVALID_VALUE, _describe_errors(error))

    return replace(row, values=MappingProxyType(model.model_dump()))


def check_minimum_age(
    row: CheckedRow,
    valid_rows: Sequence[ValidRow],
    layout: SurveyLayout = LAYOUT,
) -> CheckedRow | Rejection:
    """Reject respondents younger than the youngest age category.

    Runs after ``check_values``: it needs the parsed interview date.

    Args:
        row: Row to check, with typed values.
        valid_rows: Rows accepted so far (not used by this check).
        layout: Survey layout declaring the columns and age bands.

    Returns:
        The unchanged row or the rejection.
    """
    interview_date: datetime.date = row.values[layout.columns.interview_date]
    age = interview_date.year - row.values[layout.columns.birth_year]
    if age < layout.minimum_age:
        return Rejection(
            IssueReason.UNDERAGE,
            f"age {age} in interview year is below the minimum age "
            f"{layout.minimum_age}",
        )

    return row


def check_has_answers(
    row: CheckedRow,
    valid_rows: Sequence[ValidRow],
    layout: SurveyLayout = LAYOUT,
) -> CheckedRow | Rejection:
    """Reject a row without any awareness or usage answer.

    Args:
        row: Row to check, with typed values.
        valid_rows: Rows accepted so far (not used by this check).
        layout: Survey layout declaring the answer columns.

    Returns:
        The unchanged row or the rejection.
    """
    if all(row.values[column] is None for column in layout.answer_columns):
        return Rejection(
            IssueReason.NO_ANSWERS,
            "all awareness and usage answers are missing",
        )

    return row


def check_unique_id(
    row: CheckedRow,
    valid_rows: Sequence[ValidRow],
    layout: SurveyLayout = LAYOUT,
) -> CheckedRow | Rejection:
    """Reject a respondent ID already accepted earlier in the batch.

    Runs after ``check_values``: it needs the typed respondent ID.

    Args:
        row: Row to check, with typed values.
        valid_rows: Rows accepted so far.
        layout: Survey layout declaring the respondent ID column.

    Returns:
        The unchanged row or the rejection.
    """
    respondent_id = row.values[layout.columns.respondent_id]
    if any(valid.respondent_id == respondent_id for valid in valid_rows):
        return Rejection(
            IssueReason.DUPLICATED_ID,
            "respondent ID repeated earlier in the batch",
        )

    return row


def build_stored_id_check(
    stored_ids: Set[int], layout: SurveyLayout = LAYOUT
) -> RowCheck:
    """Build a check rejecting respondent IDs already in the database.

    The stored IDs are looked up once per batch, so the check itself
    stays pure.

    Args:
        stored_ids: Respondent IDs of the batch already stored.
        layout: Survey layout declaring the respondent ID column.

    Returns:
        A check that runs after ``check_values``.
    """

    def check_not_stored(
        row: CheckedRow, valid_rows: Sequence[ValidRow]
    ) -> CheckedRow | Rejection:
        if row.values[layout.columns.respondent_id] in stored_ids:
            return Rejection(
                IssueReason.DUPLICATED_ID,
                "respondent ID already stored in the database",
            )

        return row

    return check_not_stored


# Order matters: the later checks need the typed values.
ROW_CHECKS: Final[tuple[RowCheck, ...]] = (
    check_values,
    check_minimum_age,
    check_has_answers,
    check_unique_id,
)
