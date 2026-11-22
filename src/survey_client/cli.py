"""Command line of the survey client: ``to-json`` and ``send``.

``to-json`` turns a survey CSV file into the JSON body of a batch
upload; ``send`` posts such a file to the service and prints its
report.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Final
from urllib.error import URLError

from survey_client.batches import build_batch_body, parse_survey_csv
from survey_client.errors import CsvFormatError, UnsupportedUrlError
from survey_client.upload import HttpReply, Poster, batches_url, post_json

__all__ = [
    "DEFAULT_API_URL",
    "FILE_FORMATS",
    "Command",
    "ExitCode",
    "FileFormats",
    "main",
]

# Where ``make run-dev`` and uvicorn serve the API by default.
DEFAULT_API_URL: Final = "http://localhost:8000"


class Command(StrEnum):
    """Subcommands of the client."""

    TO_JSON = "to-json"
    SEND = "send"


class ExitCode(IntEnum):
    """Exit statuses of the client."""

    OK = 0
    REJECTED = 1  # the service replied with an error status
    INVALID_INPUT = 2  # the code argparse uses for usage errors
    UNREACHABLE = 3


@dataclass(frozen=True, slots=True)
class FileFormats:
    """Encodings and layout of the files the client reads and writes.

    Attributes:
        csv_encoding: Encoding of survey CSV files. ``utf-8-sig`` also
            reads files that start with a byte order mark, as Excel
            saves them.
        json_encoding: Encoding of JSON files.
        json_indent: Indentation of written JSON, in spaces.
    """

    csv_encoding: str = "utf-8-sig"
    json_encoding: str = "utf-8"
    json_indent: int = 2


FILE_FORMATS: Final = FileFormats()


def _build_parser(
    default_api_url: str = DEFAULT_API_URL,
) -> argparse.ArgumentParser:
    """Build the parser of the client's command line."""
    parser = argparse.ArgumentParser(
        prog="survey-client",
        description="Upload survey CSV files to the survey ETL service.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    to_json = commands.add_parser(
        Command.TO_JSON, help="convert a survey CSV file to a batch body"
    )
    to_json.add_argument("csv_file", type=Path, help="survey CSV file")
    to_json.add_argument(
        "-o", "--output", type=Path, help="JSON file (default: stdout)"
    )

    send = commands.add_parser(
        Command.SEND, help="post a batch body file to the service"
    )
    send.add_argument("json_file", type=Path, help="batch body JSON file")
    send.add_argument(
        "--api-url",
        default=default_api_url,
        help=f"base URL of the service (default: {default_api_url})",
    )

    return parser


def _convert_file(
    csv_path: Path, json_path: Path | None, formats: FileFormats = FILE_FORMATS
) -> None:
    """Write the batch body of a CSV file to a JSON file or stdout."""
    csv_text = csv_path.read_text(encoding=formats.csv_encoding)
    body = build_batch_body(parse_survey_csv(csv_text, str(csv_path)))
    json_text = json.dumps(body, indent=formats.json_indent) + "\n"

    if json_path is None:
        sys.stdout.write(json_text)
        return
    json_path.write_text(json_text, encoding=formats.json_encoding)


def _format_reply_body(body: bytes, indent: int) -> str:
    """Indent a JSON reply body; return any other body as text."""
    try:
        return json.dumps(json.loads(body), indent=indent)
    except ValueError:
        return body.decode(errors="replace")


def _print_reply(
    reply: HttpReply, formats: FileFormats = FILE_FORMATS
) -> None:
    """Print a reply body: success to stdout, errors to stderr."""
    reply_text = _format_reply_body(reply.body, formats.json_indent)
    print(reply_text, file=sys.stdout if reply.is_success else sys.stderr)


def main(argv: Sequence[str] | None = None, post: Poster = post_json) -> int:
    """Run the client's command line.

    Args:
        argv: Arguments without the program name; ``None`` reads
            ``sys.argv``.
        post: Sends a JSON body to a URL; tests pass a fake.

    Returns:
        An ``ExitCode`` value.
    """
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == Command.TO_JSON:
            _convert_file(arguments.csv_file, arguments.output)
            return ExitCode.OK
        url = batches_url(arguments.api_url)
        reply = post(url, arguments.json_file.read_bytes())

    except (URLError, TimeoutError) as error:
        print(
            f"{parser.prog}: cannot reach the service: {error}",
            file=sys.stderr,
        )
        return ExitCode.UNREACHABLE

    except (
        CsvFormatError,
        UnsupportedUrlError,
        UnicodeDecodeError,
        OSError,
    ) as error:
        print(f"{parser.prog}: {error}", file=sys.stderr)
        return ExitCode.INVALID_INPUT

    _print_reply(reply)

    return ExitCode.OK if reply.is_success else ExitCode.REJECTED
