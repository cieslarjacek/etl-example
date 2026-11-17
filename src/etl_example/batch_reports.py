"""Outcome of processing one uploaded batch, reported to the client."""

from dataclasses import dataclass

from etl_example.transform_reports import CorrectedValue
from etl_example.validation_reports import InvalidRow

__all__ = ["BatchReport"]


@dataclass(frozen=True, slots=True)
class BatchReport:
    """Outcome of processing one uploaded batch.

    Attributes:
        rows_received: Number of rows in the request.
        rows_loaded: Number of rows stored in the database.
        invalid_rows: Rows not stored, with the reason, in batch order.
        corrected_values: Values changed during transformation.
        refreshed_waves: Waves whose summaries were recalculated.
    """

    rows_received: int
    rows_loaded: int
    invalid_rows: tuple[InvalidRow, ...]
    corrected_values: tuple[CorrectedValue, ...]
    refreshed_waves: tuple[int, ...]

    def __post_init__(self) -> None:
        """Check that every received row is loaded or invalid.

        Raises:
            ValueError: If the row counts do not add up.
        """
        accounted_rows = self.rows_loaded + len(self.invalid_rows)
        if accounted_rows != self.rows_received:
            raise ValueError(
                f"{self.rows_received} rows received but {accounted_rows} "
                "loaded or invalid"
            )
