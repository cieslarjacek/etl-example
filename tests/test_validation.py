import datetime
from collections.abc import Mapping, Sequence
from types import MappingProxyType

import pytest

from etl_example.validation import (
    CheckedRow,
    Rejection,
    RowValidator,
    ValidRow,
    check_has_answers,
    check_minimum_age,
    check_unique_id,
    check_values,
)
from etl_example.validation_reports import IssueReason

VALIDATOR = RowValidator()
UNANSWERED_COLUMNS = (
    "brand1_awareness",
    "brand2_awareness",
    "brand3_awareness",
    "brand1_usage",
    "brand2_usage",
    "brand3_usage",
)


def received(raw_row: Mapping[str, object], row_number: int = 1) -> CheckedRow:
    """A row as it enters the checks."""
    values = MappingProxyType(dict(raw_row))
    return CheckedRow(row_number, values, values)


def typed(raw_row: Mapping[str, object]) -> CheckedRow:
    """A row that passed check_values, failing the test otherwise."""
    outcome = check_values(received(raw_row), [])
    assert isinstance(outcome, CheckedRow)
    return outcome


# ---- check_values ----


def test_check_values_converts_the_date(raw_row: dict[str, object]) -> None:
    outcome = check_values(received(raw_row), [])

    assert isinstance(outcome, CheckedRow)
    assert outcome.values["interview_date"] == datetime.date(2026, 9, 15)
    assert outcome.received_values["interview_date"] == "15/09/2026"


def test_check_values_accepts_unanswered_questions(
    raw_row: dict[str, object],
) -> None:
    raw_row["brand2_awareness"] = None

    outcome = check_values(received(raw_row), [])

    assert isinstance(outcome, CheckedRow)
    assert outcome.values["brand2_awareness"] is None


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("brand1_awareness", 2),
        ("brand1_usage", -1),
        ("brand1_usage", "1"),
        ("brand1_usage", True),
        ("brand1_usage", 1.0),
        ("interview_date", "31/09/2026"),
        ("interview_date", "2026-09-15"),
        ("interview_date", 20260915),
        ("wave", 0),
        ("respondent_id", 0),
    ],
)
def test_check_values_rejects_invalid_value(
    raw_row: dict[str, object], column: str, value: object
) -> None:
    raw_row[column] = value

    outcome = check_values(received(raw_row), [])

    assert isinstance(outcome, Rejection)
    assert outcome.reason is IssueReason.INVALID_VALUE
    assert outcome.details.startswith(column)


def test_check_values_rejects_missing_column(
    raw_row: dict[str, object],
) -> None:
    del raw_row["brand3_usage"]

    outcome = check_values(received(raw_row), [])

    assert outcome == Rejection(
        IssueReason.INVALID_VALUE, "brand3_usage: Field required"
    )


def test_check_values_rejects_unknown_column(
    raw_row: dict[str, object],
) -> None:
    raw_row["brand4_usage"] = 1

    outcome = check_values(received(raw_row), [])

    assert isinstance(outcome, Rejection)


# ---- check_minimum_age ----


def test_check_minimum_age_rejects_respondent_under_minimum(
    raw_row: dict[str, object],
) -> None:
    raw_row["birth_year"] = 2009

    outcome = check_minimum_age(typed(raw_row), [])

    assert outcome == Rejection(
        IssueReason.UNDERAGE,
        "age 17 in interview year is below the minimum age 18",
    )


def test_check_minimum_age_accepts_respondent_at_minimum(
    raw_row: dict[str, object],
) -> None:
    raw_row["birth_year"] = 2008
    row = typed(raw_row)

    assert check_minimum_age(row, []) is row


# ---- check_has_answers ----


def test_check_has_answers_rejects_row_without_any_answer(
    raw_row: dict[str, object],
) -> None:
    raw_row |= dict.fromkeys(UNANSWERED_COLUMNS)

    outcome = check_has_answers(typed(raw_row), [])

    assert outcome == Rejection(
        IssueReason.NO_ANSWERS, "all awareness and usage answers are missing"
    )


def test_check_has_answers_accepts_row_with_one_answer(
    raw_row: dict[str, object],
) -> None:
    raw_row |= dict.fromkeys(UNANSWERED_COLUMNS) | {"brand3_usage": 0}
    row = typed(raw_row)

    assert check_has_answers(row, []) is row


# ---- check_unique_id ----


def test_check_unique_id_rejects_id_accepted_earlier(
    raw_row: dict[str, object],
) -> None:
    accepted = [ValidRow(1, 3001, {})]

    outcome = check_unique_id(typed(raw_row), accepted)

    assert outcome == Rejection(
        IssueReason.DUPLICATED_ID,
        "respondent ID repeated earlier in the batch",
    )


def test_check_unique_id_accepts_new_id(raw_row: dict[str, object]) -> None:
    row = typed(raw_row)

    assert check_unique_id(row, [ValidRow(1, 3002, {})]) is row


# ---- RowValidator ----


def test_valid_row_is_accepted_with_typed_values(
    raw_row: dict[str, object],
) -> None:
    result = VALIDATOR.validate([raw_row])

    assert result.invalid_rows == ()
    assert result.valid_rows[0].row_number == 1
    assert result.valid_rows[0].respondent_id == 3001
    assert result.valid_rows[0].values["interview_date"] == datetime.date(
        2026, 9, 15
    )


def test_empty_batch_has_no_valid_and_no_invalid_rows() -> None:
    result = VALIDATOR.validate([])

    assert result.valid_rows == ()
    assert result.invalid_rows == ()


def test_invalid_row_keeps_values_as_received(
    raw_row: dict[str, object],
) -> None:
    raw_row["wave"] = "three"

    result = VALIDATOR.validate([raw_row])

    invalid_row = result.invalid_rows[0]
    assert invalid_row.row_number == 1
    assert invalid_row.respondent_id == 3001
    assert invalid_row.values == raw_row
    assert invalid_row.reason is IssueReason.INVALID_VALUE


def test_invalid_row_has_no_respondent_id_when_id_is_invalid(
    raw_row: dict[str, object],
) -> None:
    raw_row["respondent_id"] = "R-1"

    result = VALIDATOR.validate([raw_row])

    assert result.invalid_rows[0].respondent_id is None


def test_first_failing_check_decides_the_reason(
    raw_row: dict[str, object],
) -> None:
    raw_row |= {"birth_year": 2009, "brand1_usage": 5}

    result = VALIDATOR.validate([raw_row])

    assert result.invalid_rows[0].reason is IssueReason.INVALID_VALUE


def test_repeated_respondent_id_keeps_first_row(
    raw_row: dict[str, object],
) -> None:
    result = VALIDATOR.validate([raw_row, raw_row])

    assert [row.row_number for row in result.valid_rows] == [1]
    assert result.invalid_rows[0].row_number == 2
    assert result.invalid_rows[0].reason is IssueReason.DUPLICATED_ID


def test_row_without_answers_does_not_block_its_id(
    raw_row: dict[str, object],
) -> None:
    unanswered_first = raw_row | dict.fromkeys(UNANSWERED_COLUMNS)

    result = VALIDATOR.validate([unanswered_first, raw_row])

    assert result.invalid_rows[0].reason is IssueReason.NO_ANSWERS
    assert [row.row_number for row in result.valid_rows] == [2]


def test_rejected_row_does_not_block_its_id(
    raw_row: dict[str, object],
) -> None:
    invalid_first = raw_row | {"wave": 0}

    result = VALIDATOR.validate([invalid_first, raw_row])

    assert [row.row_number for row in result.valid_rows] == [2]


def test_rows_keep_batch_order(raw_row: dict[str, object]) -> None:
    rows = [
        raw_row | {"respondent_id": 1},
        raw_row | {"respondent_id": 2, "wave": 0},
        raw_row | {"respondent_id": 3},
        raw_row | {"respondent_id": 4, "birth_year": 2010},
    ]

    result = VALIDATOR.validate(rows)

    assert [row.row_number for row in result.valid_rows] == [1, 3]
    assert [row.row_number for row in result.invalid_rows] == [2, 4]


def test_validator_runs_injected_checks_in_order(
    raw_row: dict[str, object],
) -> None:
    calls: list[str] = []

    def first(
        row: CheckedRow, valid_rows: Sequence[ValidRow]
    ) -> CheckedRow | Rejection:
        calls.append("first")
        return check_values(row, valid_rows)

    def rejecting(
        row: CheckedRow, valid_rows: Sequence[ValidRow]
    ) -> CheckedRow | Rejection:
        calls.append("rejecting")
        return Rejection(IssueReason.UNDERAGE, "rejected by test")

    def never_reached(
        row: CheckedRow, valid_rows: Sequence[ValidRow]
    ) -> CheckedRow | Rejection:
        calls.append("never_reached")
        return row

    validator = RowValidator(checks=(first, rejecting, never_reached))

    result = validator.validate([raw_row])

    assert calls == ["first", "rejecting"]
    assert result.invalid_rows[0].details == "rejected by test"
