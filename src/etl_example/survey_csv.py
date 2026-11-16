"""Conversion of a survey CSV export to the batch upload JSON body.

Only the file structure is checked here (header and cell counts).
Values that are not integers are passed on as text, so the API's
row validation reports them like any other invalid value.
"""

import csv
import io
import json
from collections.abc import Iterator, Mapping, Sequence, Set
from typing import Final

from etl_example.survey import LAYOUT, SurveyLayout

__all__ = [
    "BATCH_KEY",
    "CsvCell",
    "CsvHeaderError",
    "CsvRowLengthError",
    "SurveyCsvError",
    "parse_survey_csv",
    "to_batch_json",
]

# Top-level key of the POST /batches body (api.BatchRequest field).
BATCH_KEY: Final = "respondents"
# Indentation of the JSON output, for readable demo output.
JSON_INDENT: Final = 2

type CsvCell = int | str | None


class SurveyCsvError(ValueError):
    """The CSV file does not have the survey structure."""


class CsvHeaderError(SurveyCsvError):
    """The CSV header does not list the survey columns in order."""

    def __init__(
        self, source: str, expected: tuple[str, ...], found: tuple[str, ...]
    ) -> None:
        """Store the source and both headers.

        Args:
            source: Name of the CSV file.
            expected: Columns the survey layout declares.
            found: Columns of the file's header.
        """
        super().__init__(source, expected, found)
        self.source = source
        self.expected = expected
        self.found = found

    def __str__(self) -> str:
        """Name the file and compare the expected and found headers."""
        found_text = ",".join(self.found) or "an empty file"
        return (
            f"{self.source}: expected header {','.join(self.expected)}; "
            f"found {found_text}"
        )


class CsvRowLengthError(SurveyCsvError):
    """A CSV row has a different number of cells than the header."""

    def __init__(
        self, source: str, line_number: int, cell_counts: tuple[int, int]
    ) -> None:
        """Store the location and the cell counts.

        Args:
            source: Name of the CSV file.
            line_number: 1-based line number of the row in the file.
            cell_counts: Expected and found number of cells.
        """
        super().__init__(source, line_number, cell_counts)
        self.source = source
        self.line_number = line_number
        self.cell_counts = cell_counts

    def __str__(self) -> str:
        """Name the file and line and compare the cell counts."""
        expected_count, found_count = self.cell_counts
        return (
            f"{self.source}, line {self.line_number}: expected "
            f"{expected_count} cells, found {found_count}"
        )


def _convert_cell(column: str, cell: str, text_columns: Set[str]) -> CsvCell:
    """Convert a cell: empty to None, integer columns to int."""
    value = cell.strip()
    if not value:
        return None
    if column in text_columns:
        return value
    try:
        return int(value)
    except ValueError:
        return value  # left for the API to reject and report


def _rows(
    lines: Iterator[list[str]], header: tuple[str, ...], source: str
) -> Iterator[list[str]]:
    """Yield the data rows, checking each has one cell per column."""
    for line_number, cells in enumerate(lines, start=2):
        if len(cells) != len(header):
            raise CsvRowLengthError(
                source, line_number, (len(header), len(cells))
            )
        yield cells


def parse_survey_csv(
    text: str, source: str, layout: SurveyLayout = LAYOUT
) -> list[dict[str, CsvCell]]:
    """Parse a survey CSV export into upload rows.

    Args:
        text: Content of the CSV file.
        source: Name of the file, used in error messages.
        layout: Survey layout declaring the columns.

    Returns:
        One dictionary per data row, keyed by column name.

    Raises:
        CsvHeaderError: If the header differs from the layout.
        CsvRowLengthError: If a row's cell count differs from the
            header's.
    """
    lines = csv.reader(io.StringIO(text))
    header = tuple(next(lines, []))
    if header != layout.input_columns:
        raise CsvHeaderError(source, layout.input_columns, header)
    text_columns = layout.text_input_columns
    return [
        {
            column: _convert_cell(column, cell, text_columns)
            for column, cell in zip(header, cells, strict=True)
        }
        for cells in _rows(lines, header, source)
    ]


def to_batch_json(
    rows: Sequence[Mapping[str, CsvCell]],
    batch_key: str = BATCH_KEY,
    indent: int = JSON_INDENT,
) -> str:
    """Serialise upload rows as the JSON body of ``POST /batches``.

    Args:
        rows: Rows parsed from a CSV export.
        batch_key: Top-level key holding the rows.
        indent: Indentation of the JSON text.

    Returns:
        The JSON text; missing values appear as ``null``.
    """
    return json.dumps({batch_key: list(rows)}, indent=indent)
