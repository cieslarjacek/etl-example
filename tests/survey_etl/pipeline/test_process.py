import logging

import pandas as pd
import pytest

from survey_etl.pipeline import PipelineOptions, process_batch
from survey_etl.storage import SurveyDatabase
from survey_etl.transform import TransformOutcome
from survey_etl.validate import IssueReason, check_values

UNANSWERED = {
    "brand1_awareness": None,
    "brand2_awareness": None,
    "brand3_awareness": None,
    "brand1_usage": None,
    "brand2_usage": None,
    "brand3_usage": None,
}


def test_valid_batch_is_loaded_and_summarised(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    report = process_batch([raw_row], database)

    assert report.rows_loaded == 1
    assert report.refreshed_waves == (3,)
    summary = database.read_wave_summary(3)
    assert summary.age_categories[0].respondents_total == 1


def test_empty_batch_loads_nothing(database: SurveyDatabase) -> None:
    report = process_batch([], database)

    assert report.rows_received == 0
    assert report.rows_loaded == 0
    assert report.invalid_rows == ()
    assert report.refreshed_waves == ()


def test_stored_id_rejects_only_its_row(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    process_batch([raw_row], database)
    new_row = raw_row | {"respondent_id": 3002}

    report = process_batch([raw_row, new_row], database)

    assert report.rows_loaded == 1
    assert report.invalid_rows[0].row_number == 1
    assert report.invalid_rows[0].reason is IssueReason.DUPLICATED_ID
    assert report.invalid_rows[0].details == (
        "respondent ID already stored in the database"
    )


def test_invalid_rows_are_reported_in_batch_order(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    process_batch([raw_row], database)
    rows = [
        raw_row | {"respondent_id": 3002} | UNANSWERED,
        raw_row,
        raw_row | {"respondent_id": 3003, "brand1_usage": 5},
    ]

    report = process_batch(rows, database)

    assert [row.reason for row in report.invalid_rows] == [
        IssueReason.NO_ANSWERS,
        IssueReason.DUPLICATED_ID,
        IssueReason.INVALID_VALUE,
    ]
    assert report.rows_loaded == 0


def test_corrected_values_are_reported(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    raw_row |= {"brand3_awareness": 0, "brand3_usage": 1}

    report = process_batch([raw_row], database)

    assert report.corrected_values[0].column == "brand3_usage"
    assert report.rows_loaded == 1


def test_refreshed_waves_include_late_rows_of_earlier_waves(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    late_row = raw_row | {"respondent_id": 2012, "wave": 2}

    report = process_batch([raw_row, late_row], database)

    assert report.refreshed_waves == (2, 3)


def test_injected_steps_replace_the_defaults(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    def tag_as_new(frame: pd.DataFrame) -> TransformOutcome:
        return TransformOutcome(frame.assign(data_status="new"))

    def add_fixed_age(frame: pd.DataFrame) -> TransformOutcome:
        return TransformOutcome(frame.assign(age=40, age_category="35-44"))

    def keep_date_text(frame: pd.DataFrame) -> TransformOutcome:
        dates = frame["interview_date"].astype(str).str.replace("-", "")
        return TransformOutcome(frame.assign(interview_date=dates))

    options = PipelineOptions(
        checks=(check_values,),
        transformers=(add_fixed_age, keep_date_text, tag_as_new),
    )

    report = process_batch([raw_row | {"birth_year": 2010}], database, options)

    assert report.rows_loaded == 1
    assert database.read_wave_summary(3).age_categories[0].age_category == (
        "35-44"
    )


def test_batch_outcome_is_logged(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="survey_etl")

    process_batch([raw_row, raw_row], database)

    assert (
        "Batch processed: 2 received, 1 loaded, 1 invalid, "
        "0 values corrected; refreshed waves (3,)"
    ) in caplog.messages


def test_each_issue_is_logged_at_debug_level(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="survey_etl")
    inconsistent_row = raw_row | {
        "respondent_id": 3002,
        "brand3_awareness": 0,
        "brand3_usage": 1,
    }

    process_batch([raw_row, raw_row, inconsistent_row], database)

    assert (
        "Row 2 invalid (duplicated_id): respondent ID repeated earlier "
        "in the batch" in caplog.messages
    )
    assert (
        "Row 3: brand3_usage corrected from 1 to 0 (usage_without_awareness)"
        in caplog.messages
    )


def test_options_without_checks_are_rejected() -> None:
    with pytest.raises(ValueError, match="'checks' must not be empty"):
        PipelineOptions(checks=())


def test_options_without_transformers_are_rejected() -> None:
    with pytest.raises(ValueError, match="'transformers' must not be empty"):
        PipelineOptions(transformers=())
