"""Survey CSV text to the JSON body of a batch upload.

The client knows the upload format, not the survey: it does not check
column names against the survey layout. The service validates every
row and reports the rows it rejects.
"""

import csv
import io
import re
from collections.abc import Sequence
from typing import Final

from survey_client.errors import (
    CsvLocation,
    InvalidHeaderError,
    MissingHeaderError,
    RowLengthError,
)

__all__ = [
    "INTEGER_PATTERN",
    "RESPONDENTS_KEY",
    "CellValue",
    "SurveyRow",
    "build_batch_body",
    "parse_cell",
    "parse_survey_csv",
]

# Whole numbers in ASCII digits only: re's \d alone would also match
# other scripts' digits, which int() accepts.
INTEGER_PATTERN: Final = re.compile(r"[+-]?\d+", re.ASCII)

# Key of the row list in the body of POST /batches.
RESPONDENTS_KEY: Final = "respondents"

type CellValue = int | str | None
type SurveyRow = dict[str, CellValue]


def parse_cell(
    text: str, integer_pattern: re.Pattern[str] = INTEGER_PATTERN
) -> CellValue:
    """Turn the text of a CSV cell into a JSON value.

    Args:
        text: Cell text as read from the file.
        integer_pattern: Pattern of text that is a whole number.

    Returns:
        ``None`` for an empty or blank cell, an ``int`` for a whole
        number, otherwise the text unchanged, so the service can
        report it.
    """
    stripped_text = text.strip()
    if not stripped_text:
        return None
    if integer_pattern.fullmatch(stripped_text):
        return int(stripped_text)

    return text


def _check_header(column_names: Sequence[str], source: str) -> None:
    """Raise unless every column name is non-empty and unique."""
    has_empty_name = any(not name.strip() for name in column_names)
    has_repeated_name = len(set(column_names)) != len(column_names)
    if has_empty_name or has_repeated_name:
        raise InvalidHeaderError(source, column_names)


def parse_survey_csv(text: str, source: str) -> tuple[SurveyRow, ...]:
    """Parse survey CSV text into rows keyed by column name.

    Blank lines are skipped. Cell values are converted by
    ``parse_cell``.

    Args:
        text: Content of a comma-separated file with a header row.
        source: Name of the file, used in error messages.

    Returns:
        One row per data line, in file order.

    Raises:
        MissingHeaderError: If the text has no header row.
        InvalidHeaderError: If a column name is empty or repeated.
        RowLengthError: If a row's field count differs from the
            header's.
    """
    reader = csv.reader(io.StringIO(text, newline=""))
    # The first non-blank line is the header.
    column_names = next((fields for fields in reader if fields), None)
    if column_names is None:
        raise MissingHeaderError(source)
    _check_header(column_names, source)

    survey_rows: list[SurveyRow] = []
    for fields in reader:
        if not fields:
            continue
        if len(fields) != len(column_names):
            location = CsvLocation(source, reader.line_num)
            raise RowLengthError(location, len(column_names), len(fields))
        survey_rows.append(
            dict(zip(column_names, map(parse_cell, fields), strict=True))
        )

    return tuple(survey_rows)


def build_batch_body(
    survey_rows: Sequence[SurveyRow], respondents_key: str = RESPONDENTS_KEY
) -> dict[str, list[SurveyRow]]:
    """Wrap survey rows in the body of a batch upload.

    Args:
        survey_rows: Rows as returned by ``parse_survey_csv``.
        respondents_key: Key of the row list in the body.

    Returns:
        The body, ready for ``json.dumps``.
    """
    return {respondents_key: list(survey_rows)}
