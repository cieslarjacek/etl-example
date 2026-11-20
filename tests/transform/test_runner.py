import pandas as pd

from survey_etl.transform import (
    CorrectedValue,
    CorrectionReason,
    TransformOutcome,
    transform_rows,
)
from tests.transform.helpers import valid_rows


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
