"""Issues found in uploaded rows, reported back to the client."""

import enum
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "IssueReason",
    "RowIssue",
    "in_batch_order",
]


class IssueReason(enum.StrEnum):
    """Why a row was dropped."""

    INVALID_VALUE = "invalid_value"
    UNDERAGE = "underage"
    DUPLICATE_IN_BATCH = "duplicate_in_batch"


@dataclass(frozen=True, slots=True)
class RowIssue:
    """A problem found in one row of a batch.

    Attributes:
        row_number: 1-based position of the row in the batch.
        respondent_id: Respondent ID, or None if it was itself invalid.
        reason: Category of the problem.
        detail: Human-readable description.
    """

    row_number: int
    respondent_id: int | None
    reason: IssueReason
    detail: str


def in_batch_order(issues: Iterable[RowIssue]) -> tuple[RowIssue, ...]:
    """Sort issues by row number keeping the order within a row.

    Args:
        issues: Issues from any pipeline step.

    Returns:
        The issues ordered as their rows appear in the batch.
    """
    return tuple(sorted(issues, key=lambda issue: issue.row_number))
