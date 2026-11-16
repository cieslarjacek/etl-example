import datetime

import pytest

from etl_example.reports import IssueReason
from etl_example.validation import (
    RowValidator,
    ValidRow,
    reject_existing_respondents,
)

VALIDATOR = RowValidator()


def test_valid_row_is_accepted_with_parsed_date(
    raw_row: dict[str, object],
) -> None:
    result = VALIDATOR.validate([raw_row])

    assert result.issues == ()
    assert result.rows[0].row_number == 1
    assert result.rows[0].respondent_id == 3001
    assert result.rows[0].values["interview_date"] == datetime.date(
        2026, 9, 15
    )


def test_unanswered_questions_are_valid(raw_row: dict[str, object]) -> None:
    raw_row["brand2_awareness"] = None

    result = VALIDATOR.validate([raw_row])

    assert result.rows[0].values["brand2_awareness"] is None


def test_empty_batch_has_no_rows_and_no_issues() -> None:
    result = VALIDATOR.validate([])

    assert result.rows == ()
    assert result.issues == ()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("brand1_awareness", 2),
        ("brand1_usage", -1),
        ("brand1_usage", "1"),
        ("brand1_usage", True),
        ("interview_date", "31/09/2026"),
        ("interview_date", "2026-09-15"),
        ("interview_date", 20260915),
        ("wave", 0),
        ("respondent_id", 0),
    ],
)
def test_invalid_value_rejects_row(
    raw_row: dict[str, object], column: str, value: object
) -> None:
    raw_row[column] = value

    result = VALIDATOR.validate([raw_row])

    assert result.rows == ()
    assert result.issues[0].reason is IssueReason.INVALID_VALUE
    assert result.issues[0].detail.startswith(column)


def test_missing_column_rejects_row(raw_row: dict[str, object]) -> None:
    del raw_row["brand3_usage"]

    result = VALIDATOR.validate([raw_row])

    assert result.issues[0].detail == "brand3_usage: Field required"


def test_unknown_column_rejects_row(raw_row: dict[str, object]) -> None:
    raw_row["brand4_usage"] = 1

    result = VALIDATOR.validate([raw_row])

    assert result.issues[0].reason is IssueReason.INVALID_VALUE


def test_issue_keeps_integer_respondent_id(raw_row: dict[str, object]) -> None:
    raw_row["wave"] = "three"

    result = VALIDATOR.validate([raw_row])

    assert result.issues[0].respondent_id == 3001


def test_issue_has_no_respondent_id_when_id_is_invalid(
    raw_row: dict[str, object],
) -> None:
    raw_row["respondent_id"] = "R-1"

    result = VALIDATOR.validate([raw_row])

    assert result.issues[0].respondent_id is None


def test_respondent_below_minimum_age_is_rejected(
    raw_row: dict[str, object],
) -> None:
    raw_row["birth_year"] = 2009

    result = VALIDATOR.validate([raw_row])

    assert result.issues[0].reason is IssueReason.UNDERAGE
    assert result.issues[0].detail == (
        "age 17 in interview year is below the minimum age 18"
    )


def test_respondent_at_minimum_age_is_accepted(
    raw_row: dict[str, object],
) -> None:
    raw_row["birth_year"] = 2008

    result = VALIDATOR.validate([raw_row])

    assert result.issues == ()


def test_repeated_respondent_id_keeps_first_row(
    raw_row: dict[str, object],
) -> None:
    result = VALIDATOR.validate([raw_row, raw_row])

    assert [row.row_number for row in result.rows] == [1]
    assert result.issues[0].row_number == 2
    assert result.issues[0].reason is IssueReason.DUPLICATE_IN_BATCH


def test_issues_follow_batch_order(raw_row: dict[str, object]) -> None:
    invalid_row = raw_row | {"respondent_id": 3002, "wave": 0}

    result = VALIDATOR.validate([raw_row, raw_row, invalid_row])

    assert [issue.row_number for issue in result.issues] == [2, 3]


def test_stored_respondent_ids_are_rejected() -> None:
    rows = [ValidRow(1, 1001, {}), ValidRow(2, 3001, {})]

    result = reject_existing_respondents(rows, frozenset({1001}))

    assert [row.respondent_id for row in result.rows] == [3001]
    assert result.issues[0].row_number == 1
    assert result.issues[0].reason is IssueReason.DUPLICATE_IN_DATABASE


def test_no_stored_respondent_ids_keeps_all_rows() -> None:
    rows = [ValidRow(1, 1001, {})]

    result = reject_existing_respondents(rows, frozenset())

    assert result.rows == tuple(rows)
    assert result.issues == ()
