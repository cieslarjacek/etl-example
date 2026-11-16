from collections.abc import Mapping, Sequence

import pandas as pd

from etl_example.reports import IssueReason
from etl_example.transform import (
    add_age_columns,
    build_frame,
    correct_usage_without_awareness,
    drop_rows_without_answers,
    format_interview_dates,
    frame_to_records,
    tag_as_new,
    transform_rows,
)
from etl_example.validation import RowValidator, ValidRow

UNANSWERED = {
    "brand1_awareness": None,
    "brand2_awareness": None,
    "brand3_awareness": None,
    "brand1_usage": None,
    "brand2_usage": None,
    "brand3_usage": None,
}


def valid_rows(raw_rows: Sequence[Mapping[str, object]]) -> list[ValidRow]:
    """Validate raw rows, failing the test if any is rejected."""
    result = RowValidator().validate(raw_rows)
    assert result.issues == ()
    return list(result.rows)


def frame_of(raw_rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    """Build the frame of raw rows that are all valid."""
    return build_frame(valid_rows(raw_rows))


def test_frame_is_indexed_by_row_number(raw_row: dict[str, object]) -> None:
    second_row = raw_row | {"respondent_id": 3002}

    frame = frame_of([raw_row, second_row])

    assert frame.index.tolist() == [1, 2]


def test_answer_columns_are_nullable_integers(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand1_usage": None}])

    assert str(frame["brand1_usage"].dtype) == "Int64"
    assert frame["brand1_usage"].isna().all()


def test_no_rows_build_empty_frame_with_all_columns() -> None:
    frame = build_frame([])

    assert frame.empty
    assert "brand3_usage" in frame.columns


def test_row_without_any_answer_is_dropped(raw_row: dict[str, object]) -> None:
    frame = frame_of([raw_row | UNANSWERED])

    result = drop_rows_without_answers(frame)

    assert result.frame.empty
    assert result.issues[0].reason is IssueReason.NO_ANSWERS
    assert result.issues[0].respondent_id == 3001


def test_row_with_one_answer_is_kept(raw_row: dict[str, object]) -> None:
    frame = frame_of([raw_row | UNANSWERED | {"brand3_usage": 0}])

    result = drop_rows_without_answers(frame)

    assert len(result.frame) == 1
    assert result.issues == ()


def test_usage_without_awareness_is_set_to_zero(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand3_awareness": 0, "brand3_usage": 1}])

    result = correct_usage_without_awareness(frame)

    assert result.frame.loc[1, "brand3_usage"] == 0
    assert result.issues[0].reason is IssueReason.USAGE_WITHOUT_AWARENESS
    assert result.issues[0].detail == (
        "brand3_usage set to 0 because brand3_awareness is not 1"
    )


def test_usage_with_unanswered_awareness_is_set_to_zero(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand3_awareness": None, "brand3_usage": 1}])

    result = correct_usage_without_awareness(frame)

    assert result.frame.loc[1, "brand3_usage"] == 0


def test_usage_with_awareness_is_unchanged(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row])

    result = correct_usage_without_awareness(frame)

    assert result.frame.loc[1, "brand1_usage"] == 1
    assert result.issues == ()


def test_unanswered_usage_stays_unanswered(raw_row: dict[str, object]) -> None:
    frame = frame_of([raw_row | {"brand3_awareness": 0, "brand3_usage": None}])

    result = correct_usage_without_awareness(frame)

    assert result.frame["brand3_usage"].isna().all()
    assert result.issues == ()


def test_age_is_interview_year_minus_birth_year(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"birth_year": 1971}])

    result = add_age_columns(frame)

    assert result.loc[1, "age"] == 55
    assert result.loc[1, "age_category"] == "55+"


def test_interview_date_is_formatted_as_yyyymmdd(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"interview_date": "01/09/2026"}])

    result = format_interview_dates(frame)

    assert result.loc[1, "interview_date"] == "20260901"


def test_rows_are_tagged_new(raw_row: dict[str, object]) -> None:
    result = tag_as_new(frame_of([raw_row]))

    assert result.loc[1, "data_status"] == "new"


def test_transform_reports_dropped_and_corrected_rows(
    raw_row: dict[str, object],
) -> None:
    unanswered_row = raw_row | UNANSWERED | {"respondent_id": 3002}
    inconsistent_row = raw_row | {
        "respondent_id": 3003,
        "brand2_awareness": 0,
        "brand2_usage": 1,
    }

    result = transform_rows(
        valid_rows([raw_row, unanswered_row, inconsistent_row])
    )

    assert result.frame.index.tolist() == [1, 3]
    assert [issue.row_number for issue in result.dropped_rows] == [2]
    assert [issue.row_number for issue in result.corrected_rows] == [3]


def test_no_rows_transform_to_empty_frame() -> None:
    result = transform_rows([])

    assert result.frame.empty
    assert {"age", "age_category", "data_status"} <= set(result.frame)


def test_records_hold_none_for_missing_values(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand1_usage": None}])

    records = frame_to_records(frame)

    assert records[0]["brand1_usage"] is None
    assert type(records[0]["brand1_awareness"]) is int
