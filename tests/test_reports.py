import pytest

from etl_example.reports import (
    BatchReport,
    IssueReason,
    RowIssue,
    in_batch_order,
)

ISSUE = RowIssue(1, 3001, IssueReason.NO_ANSWERS, "all answers missing")


def test_report_accepts_counts_that_add_up() -> None:
    report = BatchReport(2, 1, (ISSUE,), (), (3,))

    assert report.rows_loaded == 1


def test_report_rejects_rows_neither_loaded_nor_dropped() -> None:
    with pytest.raises(ValueError, match="3 rows received but 2"):
        BatchReport(3, 1, (ISSUE,), (), (3,))


def test_issues_are_ordered_by_row_keeping_order_within_row() -> None:
    later = RowIssue(4, 3004, IssueReason.UNDERAGE, "age 17")
    first_in_row = RowIssue(2, 3002, IssueReason.NO_ANSWERS, "a")
    second_in_row = RowIssue(2, 3002, IssueReason.INVALID_VALUE, "b")

    ordered = in_batch_order([later, first_in_row, second_in_row])

    assert ordered == (first_in_row, second_in_row, later)
