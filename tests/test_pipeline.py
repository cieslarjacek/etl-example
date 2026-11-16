from etl_example.database import SurveyDatabase
from etl_example.pipeline import process_batch
from etl_example.reports import IssueReason


def test_valid_batch_is_loaded_and_summarised(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    report = process_batch([raw_row], database)

    assert report.rows_loaded == 1
    assert report.refreshed_waves == (3,)
    assert (
        database.read_wave_summary(3).age_categories[0].respondents_total == 1
    )


def test_empty_batch_loads_nothing(database: SurveyDatabase) -> None:
    report = process_batch([], database)

    assert report.rows_received == 0
    assert report.rows_loaded == 0
    assert report.refreshed_waves == ()


def test_dropped_rows_are_reported_in_batch_order(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    process_batch([raw_row], database)
    invalid_row = raw_row | {"respondent_id": 3002, "brand1_usage": 5}
    unanswered_row = raw_row | {
        "respondent_id": 3003,
        "brand1_awareness": None,
        "brand2_awareness": None,
        "brand3_awareness": None,
        "brand1_usage": None,
        "brand2_usage": None,
        "brand3_usage": None,
    }

    report = process_batch([unanswered_row, raw_row, invalid_row], database)

    assert [issue.reason for issue in report.dropped_rows] == [
        IssueReason.NO_ANSWERS,
        IssueReason.DUPLICATE_IN_DATABASE,
        IssueReason.INVALID_VALUE,
    ]
    assert report.rows_loaded == 0


def test_corrected_rows_are_reported(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    raw_row |= {"brand3_awareness": 0, "brand3_usage": 1}

    report = process_batch([raw_row], database)

    assert report.corrected_rows[0].reason is (
        IssueReason.USAGE_WITHOUT_AWARENESS
    )
    assert report.rows_loaded == 1


def test_refreshed_waves_include_late_rows_of_earlier_waves(
    database: SurveyDatabase, raw_row: dict[str, object]
) -> None:
    late_row = raw_row | {"respondent_id": 2012, "wave": 2}

    report = process_batch([raw_row, late_row], database)

    assert report.refreshed_waves == (2, 3)
