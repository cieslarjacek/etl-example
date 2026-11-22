import pickle

import pytest

from survey_client import (
    CsvLocation,
    InvalidHeaderError,
    MissingHeaderError,
    RowLengthError,
    UnsupportedUrlError,
)


def test_location_rejects_line_number_below_one() -> None:
    with pytest.raises(ValueError, match="line_number"):
        CsvLocation("wave.csv", 0)


def test_missing_header_message_names_file() -> None:
    error = MissingHeaderError("wave.csv")

    assert str(error) == "wave.csv: expected a header row, found no lines"


def test_invalid_header_message_shows_header_found() -> None:
    error = InvalidHeaderError("wave.csv", ["id", "id"])

    assert str(error) == (
        "wave.csv: expected unique, non-empty column names, found ['id', 'id']"
    )


def test_row_length_message_names_line_and_counts() -> None:
    error = RowLengthError(CsvLocation("wave.csv", 4), 10, 9)

    assert str(error) == (
        "wave.csv, line 4: expected 10 fields as in the header, found 9"
    )


def test_unsupported_url_message_lists_schemes() -> None:
    error = UnsupportedUrlError("ftp://host", {"https", "http"})

    assert str(error) == (
        "ftp://host: expected a URL starting with one of http, https"
    )


@pytest.mark.parametrize(
    "error",
    [
        MissingHeaderError("wave.csv"),
        InvalidHeaderError("wave.csv", ["id", ""]),
        RowLengthError(CsvLocation("wave.csv", 4), 10, 9),
        UnsupportedUrlError("ftp://host", {"http"}),
    ],
)
def test_error_survives_pickling(error: ValueError) -> None:
    restored_error = pickle.loads(pickle.dumps(error))  # noqa: S301

    assert str(restored_error) == str(error)
