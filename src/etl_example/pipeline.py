"""The batch pipeline: validate, clean, transform, load, summarise."""

import logging
from collections.abc import Mapping, Sequence
from typing import Final

import pandas as pd

from etl_example.database import SurveyDatabase
from etl_example.reports import BatchReport, in_batch_order
from etl_example.survey import SurveyLayout
from etl_example.transform import frame_to_records, transform_rows
from etl_example.validation import RowValidator, reject_existing_respondents

__all__ = ["VALIDATOR", "process_batch"]

logger = logging.getLogger(__name__)

VALIDATOR: Final = RowValidator()


def _waves_of(frame: pd.DataFrame, layout: SurveyLayout) -> tuple[int, ...]:
    """Return the distinct waves of a frame in ascending order."""
    return tuple(sorted(int(wave) for wave in frame[layout.wave].unique()))


def _log_report(report: BatchReport) -> None:
    """Log the batch outcome, and each issue at debug level."""
    logger.info(
        "Batch processed: %d received, %d loaded, %d dropped, %d "
        "corrected; refreshed waves %s",
        report.rows_received,
        report.rows_loaded,
        len(report.dropped_rows),
        len(report.corrected_rows),
        report.refreshed_waves,
    )
    for issue in report.dropped_rows + report.corrected_rows:
        logger.debug(
            "Row %d: %s - %s", issue.row_number, issue.reason, issue.detail
        )


def process_batch(
    raw_rows: Sequence[Mapping[str, object]],
    database: SurveyDatabase,
    validator: RowValidator = VALIDATOR,
) -> BatchReport:
    """Process one uploaded batch from raw rows to refreshed summaries.

    Args:
        raw_rows: Rows decoded from the request body.
        database: Database storing respondents and summaries.
        validator: Validator of raw rows.

    Returns:
        Counts of received and loaded rows, the dropped and corrected
        rows, and the waves whose summaries were refreshed.

    Raises:
        RespondentConflictError: If a concurrent batch stored some of
            the same respondent IDs in the meantime.
    """
    validation = validator.validate(raw_rows)
    stored_ids = database.stored_respondent_ids(
        row.respondent_id for row in validation.rows
    )
    new_rows = reject_existing_respondents(validation.rows, stored_ids)
    transformed = transform_rows(new_rows.rows, validator.layout)
    records = frame_to_records(transformed.frame)
    database.load_new_respondents(records)
    dropped_rows = in_batch_order(
        validation.issues + new_rows.issues + transformed.dropped_rows
    )
    report = BatchReport(
        rows_received=len(raw_rows),
        rows_loaded=len(records),
        dropped_rows=dropped_rows,
        corrected_rows=transformed.corrected_rows,
        refreshed_waves=_waves_of(transformed.frame, validator.layout),
    )
    _log_report(report)
    return report
