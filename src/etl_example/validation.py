"""Validation of raw survey rows where they enter the application.

Each row is validated on its own, so one bad row is dropped and
reported instead of rejecting the whole batch.
"""

import datetime
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
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

from etl_example.reports import IssueReason, RowIssue, in_batch_order
from etl_example.survey import LAYOUT, SurveyLayout

__all__ = [
    "ROW_MODEL",
    "RowValidator",
    "ValidRow",
    "ValidationResult",
    "build_row_model",
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
    """A row that passed validation.

    Attributes:
        row_number: 1-based position of the row in the batch.
        respondent_id: Respondent identifier.
        values: Validated values keyed by column name.
    """

    row_number: int
    respondent_id: int
    values: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Rows that passed validation and issues of the rows that failed.

    Attributes:
        valid_rows: Valid rows in batch order.
        invalid_rows: Rejected rows with the issue reason per row.
    """

    valid_rows: tuple[ValidRow, ...]
    invalid_rows: tuple[RowIssue, ...]


class _RowRejectedError(ValueError):
    """A row failed validation - carries the issue reason and detail."""

    def __init__(self, reason: IssueReason, detail: str) -> None:
        """Store why the row was rejected.

        Args:
            reason: Category of the problem.
            detail: Human-readable description.
        """
        super().__init__(reason, detail)
        self.reason = reason
        self.detail = detail

    def __str__(self) -> str:
        """Combine the reason and the detail."""
        return f"{self.reason}: {self.detail}"


def _describe_errors(error: ValidationError) -> str:
    """Join pydantic error messages into one line per field."""
    return "; ".join(
        f"{'.'.join(map(str, details['loc']))}: {details['msg']}"
        for details in error.errors()
    )


class RowValidator:
    """Validates raw rows against a survey layout."""

    def __init__(
        self,
        row_model: type[BaseModel] = ROW_MODEL,
        layout: SurveyLayout = LAYOUT,
    ) -> None:
        """Store the row model and the survey layout.

        Args:
            row_model: Pydantic model of one row.
            layout: Survey layout the model was built from.
        """
        self._row_model = row_model
        self._layout = layout

    def validate(
        self, raw_rows: Sequence[Mapping[str, object]]
    ) -> ValidationResult:
        """Validate every row and drop .

        Args:
            raw_rows: Rows decoded from the request body.

        Returns:
            The valid rows and one issue per rejected row.
        """
        valid_rows: list[ValidRow] = []
        invalid_rows: list[RowIssue] = []
        for row_number, raw_row in enumerate(raw_rows, start=1):
            try:
                valid_rows.append(self._validate_row(row_number, raw_row))
            except _RowRejectedError as rejection:
                respondent_id = _respondent_id_of(raw_row, self._layout)
                invalid_rows.append(
                    RowIssue(
                        row_number,
                        respondent_id,
                        rejection.reason,
                        rejection.detail,
                    )
                )
        unique_rows, duplicate_issues = _drop_repeated_ids(valid_rows)

        return ValidationResult(
            tuple(unique_rows), in_batch_order(invalid_rows + duplicate_issues)
        )

    def _validate_row(
        self, row_number: int, raw_row: Mapping[str, object]
    ) -> ValidRow:
        """Validate the values of one row, then the respondent's age."""
        try:
            model = self._row_model.model_validate(raw_row)
        except ValidationError as error:
            raise _RowRejectedError(
                IssueReason.INVALID_VALUE, _describe_errors(error)
            ) from error
        values = model.model_dump()
        self._check_minimum_age(values)

        return ValidRow(
            row_number,
            values[self._layout.columns.respondent_id],
            MappingProxyType(values),
        )

    def _check_minimum_age(self, values: Mapping[str, Any]) -> None:
        """Reject respondents younger than the youngest age category."""
        layout = self._layout
        interview_date: datetime.date = values[layout.columns.interview_date]
        age = interview_date.year - values[layout.columns.birth_year]
        if age < layout.minimum_age:
            raise _RowRejectedError(
                IssueReason.UNDERAGE,
                f"age {age} in interview year is below the minimum age "
                f"{layout.minimum_age}",
            )


def _respondent_id_of(
    raw_row: Mapping[str, object], layout: SurveyLayout
) -> int | None:
    """Return the raw respondent ID if it is an integer."""
    respondent_id = raw_row.get(layout.columns.respondent_id)
    if isinstance(respondent_id, int) and not isinstance(respondent_id, bool):
        return respondent_id
    return None


def _drop_repeated_ids(
    rows: Sequence[ValidRow],
) -> tuple[list[ValidRow], list[RowIssue]]:
    """Keep the first row of each respondent ID and report the rest."""
    seen_ids: set[int] = set()
    unique_rows: list[ValidRow] = []
    issues: list[RowIssue] = []
    for row in rows:
        if row.respondent_id in seen_ids:
            issues.append(
                RowIssue(
                    row.row_number,
                    row.respondent_id,
                    IssueReason.DUPLICATE_IN_BATCH,
                    "respondent ID repeated earlier in the batch",
                )
            )
            continue
        seen_ids.add(row.respondent_id)
        unique_rows.append(row)

    return unique_rows, issues
