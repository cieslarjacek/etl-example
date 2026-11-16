import io
import json
from pathlib import Path

import pytest

from etl_example.cli import ExitStatus, main


def test_to_json_prints_batch_body(data_directory: Path) -> None:
    stdout = io.StringIO()

    status = main(["to-json", str(data_directory / "wave3.csv")], stdout)

    assert status is ExitStatus.SUCCESS
    assert len(json.loads(stdout.getvalue())["respondents"]) == 12


def test_to_json_reads_files_with_byte_order_mark(
    data_directory: Path, tmp_path: Path
) -> None:
    csv_path = tmp_path / "excel.csv"
    content = (data_directory / "wave1.csv").read_text()
    csv_path.write_text(content, encoding="utf-8-sig")
    stdout = io.StringIO()

    status = main(["to-json", str(csv_path)], stdout)

    assert status is ExitStatus.SUCCESS


def test_missing_file_fails_with_message(tmp_path: Path) -> None:
    stderr = io.StringIO()

    status = main(
        ["to-json", str(tmp_path / "absent.csv")], io.StringIO(), stderr
    )

    assert status is ExitStatus.FAILURE
    assert "absent.csv" in stderr.getvalue()


def test_wrong_header_fails_with_message(tmp_path: Path) -> None:
    csv_path = tmp_path / "other.csv"
    csv_path.write_text("id,date\n1,2\n")
    stderr = io.StringIO()

    status = main(["to-json", str(csv_path)], io.StringIO(), stderr)

    assert status is ExitStatus.FAILURE
    assert "expected header" in stderr.getvalue()


def test_missing_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as caught:
        main([], io.StringIO(), io.StringIO())

    assert caught.value.code == 2
