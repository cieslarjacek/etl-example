import datetime
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from survey_etl.validate import (
    CheckedRow,
    IssueReason,
    Rejection,
    ValidRow,
    build_stored_id_check,
    check_has_answers,
    check_minimum_age,
    check_unique_id,
    check_values,
)

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


# ---- build_stored_id_check ----


def test_stored_id_check_rejects_stored_id(
    raw_row: dict[str, object],
) -> None:
    check = build_stored_id_check(frozenset({3001}))

    outcome = check(typed(raw_row), [])

    assert outcome == Rejection(
        IssueReason.DUPLICATED_ID,
        "respondent ID already stored in the database",
    )


def test_stored_id_check_accepts_new_id(raw_row: dict[str, object]) -> None:
    check = build_stored_id_check(frozenset({1005}))
    row = typed(raw_row)

    assert check(row, []) is row
