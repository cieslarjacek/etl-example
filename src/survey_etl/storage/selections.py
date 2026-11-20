"""Which waves and age categories a summary request reads."""

from collections.abc import Sequence
from dataclasses import astuple, dataclass

from survey_etl.survey import AgeCategory

__all__ = [
    "AgeCategorySelection",
    "InvalidSelectionError",
    "WaveSelection",
]


class InvalidSelectionError(ValueError):
    """A wave or age category selection is contradictory or invalid."""

    def __init__(self, details: str) -> None:
        """Store what is wrong with the selection.

        Args:
            details: Human-readable description of the problem.
        """
        super().__init__(details)
        self.details = details


def _check_positive(numbers: Sequence[int | None], subject: str) -> None:
    """Reject numbers below 1; None means the number is not given."""
    for number in numbers:
        if number is not None and number < 1:
            raise InvalidSelectionError(
                f"{subject} numbers start at 1, found {number}"
            )


def _check_range(start: int | None, end: int | None, subject: str) -> None:
    """Reject a range whose start lies after its end."""
    if start is not None and end is not None and start > end:
        raise InvalidSelectionError(
            f"{subject} range starts at {start}, after its end {end}"
        )


@dataclass(frozen=True, slots=True)
class WaveSelection:
    """Waves to read: all, one, the latest few or a range.

    Give at most one form: ``number``, ``latest_count``, or ``start``
    and/or ``end``. Nothing given selects every wave.

    Attributes:
        number: A single wave.
        latest_count: How many of the most recent stored waves.
        start: First wave of a range; open if None.
        end: Last wave of a range; open if None.
    """

    number: int | None = None
    latest_count: int | None = None
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        """Validate the numbers and that only one form is given.

        Raises:
            InvalidSelectionError: If a number is below 1, several
                forms are given, or the range is reversed.
        """
        _check_positive(astuple(self), "wave")
        forms_given = (
            self.number is not None,
            self.latest_count is not None,
            self.start is not None or self.end is not None,
        )
        if sum(forms_given) > 1:
            raise InvalidSelectionError(
                "select waves in one way only: a single wave, the latest "
                "waves, or a range"
            )
        _check_range(self.start, self.end, "wave")


@dataclass(frozen=True, slots=True)
class AgeCategorySelection:
    """Age categories to read, by position: all, one or a range.

    Positions count from 1, youngest category first. Give at most one
    form: ``number``, or ``start`` and/or ``end``. Nothing given selects
    every category.

    Attributes:
        number: Position of a single category.
        start: Position of the first category of a range.
        end: Position of the last category of a range.
    """

    number: int | None = None
    start: int | None = None
    end: int | None = None

    def __post_init__(self) -> None:
        """Validate the positions and that only one form is given.

        Raises:
            InvalidSelectionError: If a position is below 1, both forms
                are given, or the range is reversed.
        """
        _check_positive(astuple(self), "age category")
        if self.number is not None and (
            self.start is not None or self.end is not None
        ):
            raise InvalidSelectionError(
                "select age categories in one way only: a single category "
                "or a range"
            )
        _check_range(self.start, self.end, "age category")

    def labels(self, categories: Sequence[AgeCategory]) -> tuple[str, ...]:
        """Return the labels of the selected categories, youngest first.

        Args:
            categories: The survey's age categories, youngest first.

        Returns:
            Labels of the categories at the selected positions.

        Raises:
            InvalidSelectionError: If a position exceeds the number of
                categories.
        """
        first, last = self._positions(len(categories))
        for position in (first, last):
            if position > len(categories):
                raise InvalidSelectionError(
                    f"age category {position} does not exist; there are "
                    f"{len(categories)}"
                )

        return tuple(
            category.label for category in categories[first - 1 : last]
        )

    def _positions(self, category_count: int) -> tuple[int, int]:
        """Return the first and last selected position, inclusive."""
        if self.number is not None:
            return self.number, self.number

        return self.start or 1, self.end or category_count
