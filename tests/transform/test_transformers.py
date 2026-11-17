from collections.abc import Mapping, Sequence

import pandas as pd

from etl_example.transform import (
    CorrectedValue,
    CorrectionReason,
    TransformOutcome,
    add_age_columns,
    build_frame,
    correct_usage_without_awareness,
    format_interview_dates,
    frame_to_records,
    tag_as_new,
    transform_rows,
)
from etl_example.validation import RowValidator, ValidRow


def valid_rows(raw_rows: Sequence[Mapping[str, object]]) -> list[ValidRow]:
    """Validate raw rows, failing the test if any is rejected."""
    result = RowValidator().validate(raw_rows)
    assert result.invalid_rows == ()

    return list(result.valid_rows)


def frame_of(raw_rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    """Build the frame of raw rows that are all valid."""
    return build_frame(valid_rows(raw_rows))


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


# ---- correct_usage_without_awareness ----


def test_usage_without_awareness_is_set_to_zero(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand3_awareness": 0, "brand3_usage": 1}])

    outcome = correct_usage_without_awareness(frame)

    assert outcome.frame.loc[1, "brand3_usage"] == 0
    assert outcome.corrections == (
        CorrectedValue(
            1,
            3001,
            "brand3_usage",
            1,
            0,
            CorrectionReason.USAGE_WITHOUT_AWARENESS,
        ),
    )


def test_usage_with_unanswered_awareness_is_set_to_zero(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand3_awareness": None, "brand3_usage": 1}])

    outcome = correct_usage_without_awareness(frame)

    assert outcome.frame.loc[1, "brand3_usage"] == 0
    assert len(outcome.corrections) == 1


def test_usage_with_awareness_is_unchanged(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row])

    outcome = correct_usage_without_awareness(frame)

    assert outcome.frame.loc[1, "brand1_usage"] == 1
    assert outcome.corrections == ()


def test_unanswered_usage_stays_unanswered(raw_row: dict[str, object]) -> None:
    frame = frame_of([raw_row | {"brand3_awareness": 0, "brand3_usage": None}])

    outcome = correct_usage_without_awareness(frame)

    assert outcome.frame["brand3_usage"].isna().all()
    assert outcome.corrections == ()


def test_corrections_follow_batch_order_across_brands(
    raw_row: dict[str, object],
) -> None:
    rows = [
        raw_row
        | {"respondent_id": 1, "brand3_awareness": 0, "brand3_usage": 1},
        raw_row
        | {"respondent_id": 2, "brand2_awareness": 0, "brand2_usage": 1},
    ]

    outcome = correct_usage_without_awareness(frame_of(rows))

    assert [value.row_number for value in outcome.corrections] == [1, 2]
    assert [value.column for value in outcome.corrections] == [
        "brand3_usage",
        "brand2_usage",
    ]


def test_correction_leaves_input_frame_unchanged(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"brand3_awareness": 0, "brand3_usage": 1}])

    correct_usage_without_awareness(frame)

    assert frame.loc[1, "brand3_usage"] == 1


# ---- add_age_columns ----


def test_age_is_interview_year_minus_birth_year(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"birth_year": 1971}])

    outcome = add_age_columns(frame)

    assert outcome.frame.loc[1, "age"] == 55
    assert outcome.frame.loc[1, "age_category"] == "55+"
    assert outcome.corrections == ()


# ---- format_interview_dates ----


def test_interview_date_is_formatted_as_yyyymmdd(
    raw_row: dict[str, object],
) -> None:
    frame = frame_of([raw_row | {"interview_date": "01/09/2026"}])

    outcome = format_interview_dates(frame)

    assert outcome.frame.loc[1, "interview_date"] == "20260901"


# ---- tag_as_new ----


def test_rows_are_tagged_new(raw_row: dict[str, object]) -> None:
    outcome = tag_as_new(frame_of([raw_row]))

    assert outcome.frame.loc[1, "data_status"] == "new"


# ---- transform_rows ----


def test_transform_derives_all_stored_columns(
    raw_row: dict[str, object],
) -> None:
    outcome = transform_rows(valid_rows([raw_row]))

    stored = outcome.frame.loc[1]
    assert stored["interview_date"] == "20260915"
    assert stored["age"] == 36
    assert stored["age_category"] == "35-44"
    assert stored["data_status"] == "new"


def test_transform_reports_corrections_in_batch_order(
    raw_row: dict[str, object],
) -> None:
    rows = [
        raw_row | {"respondent_id": 1},
        raw_row
        | {"respondent_id": 2, "brand2_awareness": 0, "brand2_usage": 1},
    ]

    outcome = transform_rows(valid_rows(rows))

    assert [value.row_number for value in outcome.corrections] == [2]


def test_no_rows_transform_to_empty_frame() -> None:
    outcome = transform_rows([])

    assert outcome.frame.empty
    assert {"age", "age_category", "data_status"} <= set(outcome.frame)


def test_transform_runs_injected_transformers_in_order(
    raw_row: dict[str, object],
) -> None:
    calls: list[str] = []
    correction = CorrectedValue(
        1, 3001, "brand1_usage", 1, 0, CorrectionReason.USAGE_WITHOUT_AWARENESS
    )

    def first(frame: pd.DataFrame) -> TransformOutcome:
        calls.append("first")
        return TransformOutcome(frame.assign(step="first"), (correction,))

    def second(frame: pd.DataFrame) -> TransformOutcome:
        calls.append("second after " + str(frame["step"].iloc[0]))
        return TransformOutcome(frame.assign(step="second"))

    outcome = transform_rows(valid_rows([raw_row]), (first, second))

    assert calls == ["first", "second after first"]
    assert outcome.frame.loc[1, "step"] == "second"
    assert outcome.corrections == (correction,)


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
