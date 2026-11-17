"""The batch pipeline: validate, transform, load, summarise, report."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

import pandas as pd

from etl_example.pipeline.reports import BatchReport
from etl_example.storage import SurveyDatabase
from etl_example.survey import LAYOUT, SurveyLayout
from etl_example.transform import (
    TRANSFORMERS,
    Transformer,
    frame_to_records,
    transform_rows,
)
from etl_example.validation import (
    ROW_CHECKS,
    RowCheck,
    RowValidator,
    build_stored_id_check,
    received_respondent_ids,
)

__all__ = ["DEFAULT_OPTIONS", "PipelineOptions", "process_batch"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PipelineOptions:
    """The steps a batch runs through and the layout they share.

    Attributes:
        checks: Row checks, in order; the stored-ID check is added
            after them for every batch.
        transformers: Transformers applied to the valid rows, in order.
        layout: Survey layout declaring the columns.
    """

    checks: tuple[RowCheck, ...] = ROW_CHECKS
    transformers: tuple[Transformer, ...] = TRANSFORMERS
    layout: SurveyLayout = LAYOUT

    def __post_init__(self) -> None:
        """Validate that there are steps to run.

        Raises:
            ValueError: If the checks or the transformers are empty.
        """
        if not self.checks:
            raise ValueError("'checks' must not be empty")
        if not self.transformers:
            raise ValueError("'transformers' must not be empty")


DEFAULT_OPTIONS: Final = PipelineOptions()


def _distinct_waves(
    frame: pd.DataFrame, layout: SurveyLayout
) -> tuple[int, ...]:
    """Return the distinct waves of a frame, ascending."""
    waves = frame[layout.columns.wave].unique()

    return tuple(sorted(int(wave) for wave in waves))


def _log_report(report: BatchReport) -> None:
    """Log the batch outcome, and each invalid or corrected row."""
    logger.info(
        "Batch processed: %d received, %d loaded, %d invalid, "
        "%d values corrected; refreshed waves %s",
        report.rows_received,
        report.rows_loaded,
        len(report.invalid_rows),
        len(report.corrected_values),
        report.refreshed_waves,
    )
    for invalid_row in report.invalid_rows:
        logger.debug(
            "Row %d invalid (%s): %s",
            invalid_row.row_number,
            invalid_row.reason,
            invalid_row.details,
        )
    for corrected_value in report.corrected_values:
        logger.debug(
            "Row %d: %s corrected from %d to %d (%s)",
            corrected_value.row_number,
            corrected_value.column,
            corrected_value.received,
            corrected_value.corrected,
            corrected_value.reason,
        )


def process_batch(
    raw_rows: Sequence[Mapping[str, object]],
    database: SurveyDatabase,
    options: PipelineOptions = DEFAULT_OPTIONS,
) -> BatchReport:
    """Process one uploaded batch from raw rows to refreshed summaries.

    The respondent IDs already stored are looked up first, so a stored
    ID rejects only its own row instead of the whole batch.

    Args:
        raw_rows: Rows decoded from the request body.
        database: Database storing respondents and summaries.
        options: Checks, transformers and layout to use.

    Returns:
        Counts of received and loaded rows, the invalid rows, the
        corrected values, and the waves whose summaries were refreshed.

    Raises:
        RespondentConflictError: If a concurrent batch stored one of
            the IDs between the lookup and the insert.
    """
    layout = options.layout
    stored_ids = database.stored_respondent_ids(
        received_respondent_ids(raw_rows, layout)
    )

    all_checks = (*options.checks, build_stored_id_check(stored_ids, layout))
    validation_output = RowValidator(all_checks, layout).validate(raw_rows)

    transformation_output = transform_rows(
        validation_output.valid_rows, options.transformers, layout
    )
    new_records = frame_to_records(transformation_output.frame)

    database.load_new_respondents(new_records)
    report = BatchReport(
        rows_received=len(raw_rows),
        rows_loaded=len(new_records),
        invalid_rows=validation_output.invalid_rows,
        corrected_values=transformation_output.corrections,
        refreshed_waves=_distinct_waves(transformation_output.frame, layout),
    )
    _log_report(report)

    return report
