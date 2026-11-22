import json
from collections.abc import Callable
from pathlib import Path
from urllib.error import URLError

import pytest

from survey_client import HttpReply, Poster
from survey_client.cli import ExitCode, main

CSV_TEXT = (
    "respondent_id,interview_date,wave,brand1_usage\n1001,02/03/2026,1,\n"
)
BATCH_BODY = {
    "respondents": [
        {
            "respondent_id": 1001,
            "interview_date": "02/03/2026",
            "wave": 1,
            "brand1_usage": None,
        }
    ]
}
API_URL = "http://survey.test:8000"

type PostCalls = list[tuple[str, bytes]]


def recording_post(reply: HttpReply, calls: PostCalls) -> Poster:
    """A fake post that records its calls and returns a fixed reply."""

    def post(url: str, body: bytes) -> HttpReply:
        calls.append((url, body))
        return reply

    return post


def failing_post(error: Exception) -> Poster:
    """A fake post that raises an error."""

    def post(url: str, body: bytes) -> HttpReply:
        raise error

    return post


@pytest.fixture
def csv_path(tmp_path: Path) -> Path:
    path = tmp_path / "wave1.csv"
    path.write_text(CSV_TEXT, encoding="utf-8")
    return path


@pytest.fixture
def json_path(tmp_path: Path) -> Path:
    path = tmp_path / "wave1.json"
    path.write_text(json.dumps(BATCH_BODY), encoding="utf-8")
    return path


type SendRunner = Callable[[Poster], int]


@pytest.fixture
def run_send(json_path: Path) -> SendRunner:
    """Run ``send`` on the batch file with a given post function."""

    def run(post: Poster) -> int:
        return main(["send", str(json_path), "--api-url", API_URL], post)

    return run


# ---- to-json ----


def test_to_json_prints_batch_body(
    csv_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["to-json", str(csv_path)])

    assert exit_code == ExitCode.OK
    assert json.loads(capsys.readouterr().out) == BATCH_BODY


def test_to_json_writes_output_file(csv_path: Path, tmp_path: Path) -> None:
    output_path = tmp_path / "body.json"

    exit_code = main(["to-json", str(csv_path), "--output", str(output_path)])

    assert exit_code == ExitCode.OK
    assert json.loads(output_path.read_text(encoding="utf-8")) == BATCH_BODY


def test_to_json_reads_file_with_byte_order_mark(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv_path = tmp_path / "excel.csv"
    csv_path.write_text(CSV_TEXT, encoding="utf-8-sig")

    main(["to-json", str(csv_path)])

    assert json.loads(capsys.readouterr().out) == BATCH_BODY


def test_to_json_reports_malformed_csv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv_path = tmp_path / "short.csv"
    csv_path.write_text("respondent_id,wave\n1001\n", encoding="utf-8")

    exit_code = main(["to-json", str(csv_path)])

    assert exit_code == ExitCode.INVALID_INPUT
    assert "short.csv, line 2: expected 2 fields" in capsys.readouterr().err


def test_to_json_reports_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["to-json", str(tmp_path / "absent.csv")])

    assert exit_code == ExitCode.INVALID_INPUT
    assert "absent.csv" in capsys.readouterr().err


def test_to_json_reports_file_that_is_not_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    csv_path = tmp_path / "latin1.csv"
    csv_path.write_bytes(
        "respondent_id,city\n1001,M\xe1laga\n".encode("latin-1")
    )

    exit_code = main(["to-json", str(csv_path)])

    assert exit_code == ExitCode.INVALID_INPUT
    assert "utf-8" in capsys.readouterr().err


# ---- send ----


def test_send_posts_file_to_batches_url(
    run_send: SendRunner, json_path: Path
) -> None:
    calls: PostCalls = []

    run_send(recording_post(HttpReply(200, b"{}"), calls))

    assert calls == [(f"{API_URL}/batches", json_path.read_bytes())]


def test_send_prints_indented_report_on_success(
    run_send: SendRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    reply = HttpReply(200, b'{"rows_loaded":1}')

    exit_code = run_send(recording_post(reply, []))

    assert exit_code == ExitCode.OK
    assert capsys.readouterr().out == '{\n  "rows_loaded": 1\n}\n'


def test_send_prints_rejection_to_stderr(
    run_send: SendRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    reply = HttpReply(409, b'{"detail":"conflict"}')

    exit_code = run_send(recording_post(reply, []))

    captured = capsys.readouterr()
    assert exit_code == ExitCode.REJECTED
    assert (captured.out, json.loads(captured.err)) == (
        "",
        {"detail": "conflict"},
    )


def test_send_prints_non_json_reply_as_text(
    run_send: SendRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    reply = HttpReply(502, b"Bad Gateway")

    run_send(recording_post(reply, []))

    assert capsys.readouterr().err == "Bad Gateway\n"


@pytest.mark.parametrize(
    "error", [URLError("connection refused"), TimeoutError("timed out")]
)
def test_send_reports_unreachable_service(
    run_send: SendRunner,
    error: Exception,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = run_send(failing_post(error))

    assert exit_code == ExitCode.UNREACHABLE
    assert "cannot reach the service" in capsys.readouterr().err


def test_send_reports_unsupported_url(
    json_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: PostCalls = []
    post = recording_post(HttpReply(200, b"{}"), calls)

    exit_code = main(["send", str(json_path), "--api-url", "ftp://x"], post)

    assert (exit_code, calls) == (ExitCode.INVALID_INPUT, [])
    assert "ftp://x" in capsys.readouterr().err


def test_send_reports_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    post = recording_post(HttpReply(200, b"{}"), [])

    exit_code = main(["send", str(tmp_path / "absent.json")], post)

    assert exit_code == ExitCode.INVALID_INPUT
    assert "absent.json" in capsys.readouterr().err


# ---- command line ----


def test_missing_command_is_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        main([])

    assert raised.value.code == ExitCode.INVALID_INPUT
