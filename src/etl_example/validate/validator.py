"""Validation of raw survey rows where they enter the application.

Every row runs through a sequence of checks. A check returns the row
or a ``Rejection``. The first rejection stops the row: it is reported as
invalid and not passed on.
A row that passes every check is appended to the valid rows, which
later checks see, so a repeated respondent ID keeps its first row.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from etl_example.survey import LAYOUT, SurveyLayout
from etl_example.validate.checks import (
    ROW_CHECKS,
    CheckedRow,
    Rejection,
    RowCheck,
    ValidRow,
)
from etl_example.validate.reports import InvalidRow

__all__ = [
    "RowValidator",
    "ValidationResult",
    "received_respondent_ids",
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
