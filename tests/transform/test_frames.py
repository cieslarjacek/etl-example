from etl_example.transform import (
    build_frame,
    frame_to_records,
)
from tests.transform.helpers import frame_of

# ---- build_frame ----


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


# ---- frame_to_records ----


def test_records_hold_none_for_unanswered_questions(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand1_usage": None}])

    records = frame_to_records(frame)

    assert records[0]["brand1_usage"] is None
    assert type(records[0]["brand1_awareness"]) is int


def test_records_of_empty_frame_are_empty() -> None:
    assert frame_to_records(build_frame([])) == ()
