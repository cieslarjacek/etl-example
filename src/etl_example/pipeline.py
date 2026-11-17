"""The batch pipeline: validate, transform, load, summarise, report."""

import logging
from collections.abc import Mapping, Sequence

import pandas as pd

from etl_example.batch_reports import BatchReport
from etl_example.database import SurveyDatabase
from etl_example.survey_layout import LAYOUT, SurveyLayout
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

__all__ = ["process_batch"]

logger = logging.getLogger(__name__)


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
    checks: Sequence[RowCheck] = ROW_CHECKS,
    transformers: Sequence[Transformer] = TRANSFORMERS,
    layout: SurveyLayout = LAYOUT,
) -> BatchReport:
    """Process one uploaded batch from raw rows to refreshed summaries.

    The respondent IDs already stored are looked up first, so a stored
    ID rejects only its own row instead of the whole batch.

    Args:
        raw_rows: Rows decoded from the request body.
        database: Database storing respondents and summaries.
        checks: Row checks to run before the stored-ID check.
        transformers: Transformers to apply to the valid rows.
        layout: Survey layout declaring the columns.

    Returns:
        Counts of received and loaded rows, the invalid rows, the
        corrected values, and the waves whose summaries were refreshed.

    Raises:
        RespondentConflictError: If a concurrent batch stored one of
            the IDs between the lookup and the insert.
    """
    stored_ids = database.stored_respondent_ids(
        received_respondent_ids(raw_rows, layout)
    )
    all_checks = (*checks, build_stored_id_check(stored_ids, layout))
    validation = RowValidator(all_checks, layout).validate(raw_rows)
    transformed = transform_rows(validation.valid_rows, transformers, layout)
    records = frame_to_records(transformed.frame)
    database.load_new_respondents(records)
    report = BatchReport(
        rows_received=len(raw_rows),
        rows_loaded=len(records),
        invalid_rows=validation.invalid_rows,
        corrected_values=transformed.corrections,
        refreshed_waves=_distinct_waves(transformed.frame, layout),
    )
    _log_report(report)

    return report
