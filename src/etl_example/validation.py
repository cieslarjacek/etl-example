"""Validation of raw survey rows where they enter the application.

Every row runs through a sequence of checks. A check returns the row
or a ``Rejection``. The first rejection stops the row: it is reported as
invalid and not passed on.
A row that passes every check is appended to the valid rows, which
later checks see, so a repeated respondent ID keeps its first row.
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

from etl_example.survey_layout import LAYOUT, SurveyLayout
from etl_example.validation_reports import InvalidRow, IssueReason

__all__ = [
    "ROW_CHECKS",
    "ROW_MODEL",
    "CheckedRow",
    "Rejection",
    "RowCheck",
    "RowValidator",
    "ValidRow",
    "ValidationResult",
    "build_row_model",
    "build_stored_id_check",
    "check_has_answers",
    "check_minimum_age",
    "check_unique_id",
    "check_values",
    "received_respondent_ids",
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


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Rows that passed every check and rows that were rejected.

    Attributes:
        valid_rows: Valid rows in batch order.
        invalid_rows: Rejected rows with the reason, in batch order.
    """

    valid_rows: tuple[ValidRow, ...]
    invalid_rows: tuple[InvalidRow, ...]


def _integer_or_none(value: object) -> int | None:
    """Return the value if it is an int but not a bool, else None."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


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


def received_respondent_ids(
    raw_rows: Sequence[Mapping[str, object]], layout: SurveyLayout = LAYOUT
) -> frozenset[int]:
    """Return the respondent IDs of raw rows that are integers.

    Args:
        raw_rows: Rows decoded from the request body.
        layout: Survey layout declaring the respondent ID column.

    Returns:
        The distinct respondent IDs that are integers.
    """
    respondent_ids = (
        _integer_or_none(raw_row.get(layout.columns.respondent_id))
        for raw_row in raw_rows
    )

    return frozenset(
        respondent_id
        for respondent_id in respondent_ids
        if respondent_id is not None
    )


# Order matters: the later checks need the typed values.
ROW_CHECKS: Final[tuple[RowCheck, ...]] = (
    check_values,
    check_minimum_age,
    check_has_answers,
    check_unique_id,
)


class RowValidator:
    """Runs every row through the checks, in order."""

    def __init__(
        self,
        checks: Sequence[RowCheck] = ROW_CHECKS,
        layout: SurveyLayout = LAYOUT,
    ) -> None:
        """Store the checks and the survey layout.

        Args:
            checks: Sequence of checks every row must pass (in order).
            layout: Survey layout including the respondent ID column.
        """
        self._checks = tuple(checks)
        self._layout = layout

    def validate(
        self, raw_rows: Sequence[Mapping[str, object]]
    ) -> ValidationResult:
        """Validate every row, keeping valid and invalid rows apart.

        Args:
            raw_rows: Rows decoded from the request body.

        Returns:
            The valid rows and the invalid rows, each in batch order.
        """
        valid_rows: list[ValidRow] = []
        invalid_rows: list[InvalidRow] = []

        for row_number, raw_row in enumerate(raw_rows, start=1):
            received_values = MappingProxyType(dict(raw_row))
            # Create the row's starting state for the checks.
            received_row = CheckedRow(
                row_number, received_values, received_values
            )

            check_outcome = self._run_checks(received_row, valid_rows)
            if isinstance(check_outcome, Rejection):
                invalid_rows.append(
                    self._invalid_row(received_row, check_outcome)
                )
                continue
            valid_rows.append(self._valid_row(check_outcome))

        return ValidationResult(tuple(valid_rows), tuple(invalid_rows))

    def _run_checks(
        self, row: CheckedRow, valid_rows: Sequence[ValidRow]
    ) -> CheckedRow | Rejection:
        """Pass the row through the checks until one rejects it."""
        for check in self._checks:
            outcome = check(row, valid_rows)
            if isinstance(outcome, Rejection):
                return outcome
            row = outcome

        return row

    def _valid_row(self, row: CheckedRow) -> ValidRow:
        """Turn a row that passed every check into a valid row."""
        respondent_id = row.values[self._layout.columns.respondent_id]

        return ValidRow(row.row_number, respondent_id, row.values)

    def _invalid_row(
        self, row: CheckedRow, rejection: Rejection
    ) -> InvalidRow:
        """Turn a rejected row into an invalid row for the report."""
        respondent_id = row.received_values.get(
            self._layout.columns.respondent_id
        )

        return InvalidRow(
            row.row_number,
            _integer_or_none(respondent_id),
            row.received_values,
            rejection.reason,
            rejection.details,
        )
