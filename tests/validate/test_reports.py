import pytest

from etl_example.validate import InvalidRow, IssueReason


def test_invalid_row_cannot_be_changed() -> None:
    row = InvalidRow(2, 3002, {}, IssueReason.INVALID_VALUE, "b")

    with pytest.raises(AttributeError):
        row.reason = IssueReason.UNDERAGE  # type: ignore[misc]


def test_invalid_row_values_are_read_only() -> None:
    row = InvalidRow(2, 3002, {"wave": 0}, IssueReason.INVALID_VALUE, "b")

    with pytest.raises(TypeError):
        row.values["wave"] = 3  # type: ignore[index]


def test_invalid_row_keeps_values_when_caller_changes_its_dict() -> None:
    received_values: dict[str, object] = {"wave": 0}
    row = InvalidRow(2, 3002, received_values, IssueReason.INVALID_VALUE, "b")

    received_values["wave"] = 3

    assert row.values == {"wave": 0}
