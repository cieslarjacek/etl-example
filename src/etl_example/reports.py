"""Result values returned by the pipeline and the summary queries."""

import enum
from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "AgeCategorySummary",
    "BatchReport",
    "BrandTotal",
    "IssueReason",
    "RowIssue",
    "WaveSummary",
    "in_batch_order",
]


class IssueReason(enum.StrEnum):
    """Why a row was dropped or corrected."""

    INVALID_VALUE = "invalid_value"
    UNDERAGE = "underage"
    DUPLICATE_IN_BATCH = "duplicate_in_batch"
    DUPLICATE_IN_DATABASE = "duplicate_in_database"
    NO_ANSWERS = "no_answers"
    USAGE_WITHOUT_AWARENESS = "usage_without_awareness"


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
    """Sort issues by row number, keeping the order within a row.

    Args:
        issues: Issues from any pipeline step.

    Returns:
        The issues ordered as their rows appear in the batch.
    """
    return tuple(sorted(issues, key=lambda issue: issue.row_number))


@dataclass(frozen=True, slots=True)
class BatchReport:
    """Outcome of processing one uploaded batch.

    Attributes:
        rows_received: Number of rows in the request.
        rows_loaded: Number of rows stored in the database.
        dropped_rows: Rows not stored, with the reason.
        corrected_rows: Values changed during transformation.
        refreshed_waves: Waves whose summaries were recalculated.
    """

    rows_received: int
    rows_loaded: int
    dropped_rows: tuple[RowIssue, ...]
    corrected_rows: tuple[RowIssue, ...]
    refreshed_waves: tuple[int, ...]

    def __post_init__(self) -> None:
        """Check that every received row is loaded or dropped.

        Raises:
            ValueError: If the row counts do not add up.
        """
        accounted_rows = self.rows_loaded + len(self.dropped_rows)
        if accounted_rows != self.rows_received:
            raise ValueError(
                f"{self.rows_received} rows received but {accounted_rows} "
                "loaded or dropped"
            )


@dataclass(frozen=True, slots=True)
class BrandTotal:
    """Awareness and usage counts of one brand.

    Attributes:
        brand: Brand identifier.
        awareness_total: Respondents aware of the brand.
        usage_total: Respondents using the brand.
    """

    brand: str
    awareness_total: int
    usage_total: int


@dataclass(frozen=True, slots=True)
class AgeCategorySummary:
    """Wave totals for one age category.

    Attributes:
        age_category: Age category label.
        respondents_total: Respondents in the category.
        brands: Awareness and usage counts per brand.
    """

    age_category: str
    respondents_total: int
    brands: tuple[BrandTotal, ...]


@dataclass(frozen=True, slots=True)
class WaveSummary:
    """Totals of one wave, broken down by age category.

    Attributes:
        wave: Wave number.
        age_categories: Totals per age category, youngest first.
    """

    wave: int
    age_categories: tuple[AgeCategorySummary, ...]
