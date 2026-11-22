"""Errors raised for input the client cannot use."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

__all__ = [
    "CsvFormatError",
    "CsvLocation",
    "InvalidHeaderError",
    "MissingHeaderError",
    "RowLengthError",
    "UnsupportedUrlError",
]


@dataclass(frozen=True, slots=True)
class CsvLocation:
    """A line of a CSV file.

    Attributes:
        source: Name of the file, used in error messages.
        line_number: 1-based line number in the file.
    """

    source: str
    line_number: int

    def __post_init__(self) -> None:
        """Reject line numbers below 1.

        Raises:
            ValueError: If ``line_number`` is below 1.
        """
        if self.line_number < 1:
            message = f"line_number must be at least 1, got {self.line_number}"
            raise ValueError(message)


class CsvFormatError(ValueError):
    """A CSV file the client cannot turn into survey rows."""


class MissingHeaderError(CsvFormatError):
    """The CSV file has no header row."""

    def __init__(self, source: str) -> None:
        """Store the file name.

        Args:
            source: Name of the file.
        """
        super().__init__(source)
        self.source = source

    def __str__(self) -> str:
        """Name the file and what was expected."""
        return f"{self.source}: expected a header row, found no lines"


class InvalidHeaderError(CsvFormatError):
    """The header row has empty or repeated column names."""

    def __init__(self, source: str, column_names: Sequence[str]) -> None:
        """Store the file name and the header as found.

        Args:
            source: Name of the file.
            column_names: Column names in the header row.
        """
        super().__init__(source, column_names)
        self.source = source
        self.column_names = tuple(column_names)

    def __str__(self) -> str:
        """Name the file and the header found."""
        return (
            f"{self.source}: expected unique, non-empty column names, "
            f"found {list(self.column_names)}"
        )


class RowLengthError(CsvFormatError):
    """A row has a different number of fields than the header."""

    def __init__(
        self, location: CsvLocation, expected_count: int, found_count: int
    ) -> None:
        """Store where the row is and both field counts.

        Args:
            location: File and line of the row.
            expected_count: Number of columns in the header.
            found_count: Number of fields in the row.
        """
        super().__init__(location, expected_count, found_count)
        self.location = location
        self.expected_count = expected_count
        self.found_count = found_count

    def __str__(self) -> str:
        """Name the file, the line and both field counts."""
        return (
            f"{self.location.source}, line {self.location.line_number}: "
            f"expected {self.expected_count} fields as in the header, "
            f"found {self.found_count}"
        )


class UnsupportedUrlError(ValueError):
    """The API URL does not use an allowed scheme."""

    def __init__(self, url: str, allowed_schemes: Collection[str]) -> None:
        """Store the URL and the schemes the client accepts.

        Args:
            url: URL as given.
            allowed_schemes: Schemes the client accepts.
        """
        super().__init__(url, allowed_schemes)
        self.url = url
        self.allowed_schemes = tuple(sorted(allowed_schemes))

    def __str__(self) -> str:
        """Name the URL and the accepted schemes."""
        return (
            f"{self.url}: expected a URL starting with one of "
            f"{', '.join(self.allowed_schemes)}"
        )
