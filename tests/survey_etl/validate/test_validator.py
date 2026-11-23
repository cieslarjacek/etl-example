import datetime
from collections.abc import Mapping, Sequence

from survey_etl.validate import (
    CheckedRow,
    IssueReason,
    Rejection,
    RowValidator,
    ValidRow,
    check_values,
    received_respondent_ids,
)

VALIDATOR = RowValidator()
UNANSWERED_COLUMNS = (
    "brand1_awareness",
    "brand2_awareness",
    "brand3_awareness",
    "brand1_usage",
    "brand2_usage",
    "brand3_usage",
)


# ---- received_respondent_ids ----


def test_received_ids_leave_out_ids_that_are_not_integers(
    raw_row: dict[str, object],
) -> None:
    rows: list[Mapping[str, object]] = [
        raw_row,
        raw_row | {"respondent_id": "R-1"},
        raw_row | {"respondent_id": True},
        raw_row | {"respondent_id": None},
        {"wave": 3},
    ]

    assert received_respondent_ids(rows) == frozenset({3001})


def test_received_ids_of_empty_batch_are_empty() -> None:
    assert received_respondent_ids([]) == frozenset()


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
