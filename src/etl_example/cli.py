"""Command-line interface.

``etl-example to-json PATH`` prints the JSON body of ``POST /batches``
for a survey CSV export, so it can be piped into ``curl``.
"""

import argparse
import enum
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TextIO

from etl_example.survey_csv import (
    CsvCell,
    SurveyCsvError,
    parse_survey_csv,
    to_batch_json,
)

__all__ = ["ExitStatus", "main"]

# utf-8-sig also reads files saved by Excel with a byte-order mark.
CSV_ENCODING: Final = "utf-8-sig"


class ExitStatus(enum.IntEnum):
    """Process exit status of the command line."""

    SUCCESS = 0
    FAILURE = 1


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with its sub-commands."""
    parser = argparse.ArgumentParser(
        prog="etl-example", description="Tools for the survey ETL API."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    to_json = commands.add_parser(
        "to-json",
        help="print a survey CSV export as the JSON body of POST /batches",
    )
    to_json.add_argument("csv_path", type=Path, help="survey CSV file")
    return parser


def _read_rows(
    csv_path: Path, encoding: str = CSV_ENCODING
) -> list[dict[str, CsvCell]]:
    """Read and parse a survey CSV file."""
    return parse_survey_csv(
        csv_path.read_text(encoding=encoding), str(csv_path)
    )


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Run the command line.

    Args:
        argv: Arguments without the program name; None reads
            ``sys.argv``.
        stdout: Stream receiving the JSON output.
        stderr: Stream receiving error messages.

    Returns:
        The process exit status.
    """
    arguments = _build_parser().parse_args(argv)
    csv_path: Path = arguments.csv_path
    try:
        rows = _read_rows(csv_path)
    except (OSError, SurveyCsvError) as error:
        print(f"etl-example: {error}", file=stderr)
        return ExitStatus.FAILURE
    print(to_batch_json(rows), file=stdout)
    return ExitStatus.SUCCESS
