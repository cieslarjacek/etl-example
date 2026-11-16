from etl_example.reports import IssueReason, RowIssue, in_batch_order


def test_issues_are_ordered_by_row_keeping_order_within_row() -> None:
    later = RowIssue(4, 3004, IssueReason.UNDERAGE, "age 17")
    first_in_row = RowIssue(2, 3002, IssueReason.DUPLICATE_IN_BATCH, "a")
    second_in_row = RowIssue(2, 3002, IssueReason.INVALID_VALUE, "b")

    ordered = in_batch_order([later, first_in_row, second_in_row])

    assert ordered == (first_in_row, second_in_row, later)
