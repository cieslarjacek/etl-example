import pytest

from etl_example.batch_reports import BatchReport
from etl_example.validation_reports import InvalidRow, IssueReason

INVALID_ROW = InvalidRow(1, 3001, {}, IssueReason.NO_ANSWERS, "no answers")


def test_report_accepts_counts_that_add_up() -> None:
    report = BatchReport(2, 1, (INVALID_ROW,), (), (3,))

    assert report.rows_loaded == 1


def test_report_rejects_rows_neither_loaded_nor_invalid() -> None:
    with pytest.raises(ValueError, match="3 rows received but 2"):
        BatchReport(3, 1, (INVALID_ROW,), (), (3,))
