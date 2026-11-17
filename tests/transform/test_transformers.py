from etl_example.transform import (
    CorrectedValue,
    CorrectionReason,
    add_age_columns,
    correct_usage_without_awareness,
    format_interview_dates,
    tag_as_new,
)
from tests.transform.helpers import frame_of

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
