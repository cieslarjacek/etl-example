"""Tracking-survey layout: brands, age categories, columns, formats.

Every fact about the survey layout is declared once, in ``LAYOUT``.
The other modules receive a ``SurveyLayout`` and iterate over it
instead of repeating column names.
"""

from dataclasses import astuple, dataclass, field
from itertools import pairwise
from typing import Final

__all__ = [
    "LAYOUT",
    "AgeCategory",
    "AgeOutOfRangeError",
    "ColumnNames",
    "SurveyLayout",
]


@dataclass(frozen=True, slots=True)
class AgeCategory:
    """A closed or open-ended age band in years.

    Attributes:
        label: Name shown in reports, e.g. ``"25-34"``.
        minimum_age: Lowest age in the band.
        maximum_age: Highest age in the band; None for an open band.
    """

    label: str
    minimum_age: int
    maximum_age: int | None = None

    def __post_init__(self) -> None:
        """Validate the bounds.

        Raises:
            ValueError: If a bound is negative or the band is empty.
        """
        if self.minimum_age < 0:
            raise ValueError(
                f"age category {self.label!r}: 'minimum_age' must not be "
                f"negative, found {self.minimum_age}"
            )
        if self.maximum_age is not None and (
            self.maximum_age < self.minimum_age
        ):
            raise ValueError(
                f"age category {self.label!r}: 'maximum_age' "
                f"{self.maximum_age} is below 'minimum_age' {self.minimum_age}"
            )

    def contains(self, age: int) -> bool:
        """Tell whether an age falls into the band.

        Args:
            age: Age in years.

        Returns:
            True if the age lies within the bounds.
        """
        if age < self.minimum_age:
            return False
        return self.maximum_age is None or age <= self.maximum_age


class AgeOutOfRangeError(ValueError):
    """No age category contains the given age."""

    def __init__(self, age: int) -> None:
        """Store the age that matched no category.

        Args:
            age: Age in years.
        """
        super().__init__(age)
        self.age = age

    def __str__(self) -> str:
        """Name the age that matched no category."""
        return f"no age category contains age {self.age}"


@dataclass(frozen=True, slots=True)
class ColumnNames:
    """Names of the survey columns that do not depend on the brands.

    Attributes:
        respondent_id: Column with the respondent identifier.
        interview_date: Column with the interview date.
        wave: Column with the wave number.
        birth_year: Column with the year of birth.
        age: Derived column with the age in the interview year.
        age_category: Derived column with the age category label.
        data_status: Column with the processing status.
    """

    respondent_id: str = "respondent_id"
    interview_date: str = "interview_date"
    wave: str = "wave"
    birth_year: str = "birth_year"
    age: str = "age"
    age_category: str = "age_category"
    data_status: str = "data_status"

    def __post_init__(self) -> None:
        """Validate that the names are non-empty and distinct.

        Raises:
            ValueError: If a name is empty or used twice.
        """
        names = astuple(self)
        if not all(names) or len(set(names)) != len(names):
            raise ValueError(
                f"column names must be non-empty and unique, found {names}"
            )


@dataclass(frozen=True, slots=True)
class SurveyLayout:
    """Brands, age bands, date formats and column names of a survey.

    Attributes:
        brands: Brand identifiers, in reporting order.
        age_categories: Age bands, youngest first, without gaps.
        input_date_format: ``strptime`` format of incoming dates.
        storage_date_format: ``strftime`` format of stored dates.
        columns: Names of the columns that do not depend on brands.
    """

    brands: tuple[str, ...]
    age_categories: tuple[AgeCategory, ...]
    input_date_format: str
    storage_date_format: str
    columns: ColumnNames = field(default_factory=ColumnNames)

    def __post_init__(self) -> None:
        """Validate the brands and the age bands.

        Raises:
            ValueError: If brands are missing or repeated, or the age
                bands are missing, unordered, overlapping or gapped (an
                open-ended band can only be the last one).
        """
        if not self.brands or len(set(self.brands)) != len(self.brands):
            raise ValueError(
                f"'brands' must be non-empty and unique, found {self.brands}"
            )
        if not self.age_categories:
            raise ValueError("'age_categories' must not be empty")
        for younger, older in pairwise(self.age_categories):
            if younger.maximum_age != older.minimum_age - 1:
                raise ValueError(
                    f"age categories {younger.label!r} and "
                    f"{older.label!r} must be adjacent"
                )

    def awareness_column(self, brand: str) -> str:
        """Return the awareness dummy column of a brand.

        Args:
            brand: Brand identifier, e.g. ``"brand1"``.

        Returns:
            Column name, e.g. ``"brand1_awareness"``.
        """
        return f"{brand}_awareness"

    def usage_column(self, brand: str) -> str:
        """Return the usage dummy column of a brand.

        Args:
            brand: Brand identifier, e.g. ``"brand1"``.

        Returns:
            Column name, e.g. ``"brand1_usage"``.
        """
        return f"{brand}_usage"

    @property
    def answer_columns(self) -> tuple[str, ...]:
        """Awareness columns of all brands, then usage columns."""
        awareness_columns = tuple(map(self.awareness_column, self.brands))
        usage_columns = tuple(map(self.usage_column, self.brands))

        return awareness_columns + usage_columns

    @property
    def input_columns(self) -> tuple[str, ...]:
        """Columns of an incoming row, in file order."""
        return (
            self.columns.respondent_id,
            self.columns.interview_date,
            self.columns.wave,
            self.columns.birth_year,
            *self.answer_columns,
        )

    @property
    def minimum_age(self) -> int:
        """Youngest age any age category accepts."""
        return self.age_categories[0].minimum_age

    def age_category_label(self, age: int) -> str:
        """Return the label of the category containing an age.

        Args:
            age: Age in years.

        Returns:
            Label of the category containing the age.

        Raises:
            AgeOutOfRangeError: If no category contains the age.
        """
        for category in self.age_categories:
            if category.contains(age):
                return category.label
        raise AgeOutOfRangeError(age)


LAYOUT: Final = SurveyLayout(
    brands=("brand1", "brand2", "brand3"),
    age_categories=(
        AgeCategory("18-24", 18, 24),
        AgeCategory("25-34", 25, 34),
        AgeCategory("35-44", 35, 44),
        AgeCategory("45-54", 45, 54),
        AgeCategory("55+", 55),
    ),
    # Fieldwork exports write "DD/MM/YYYY" format.
    input_date_format="%d/%m/%Y",
    # Storage uses "YYYYMMDD" format.
    storage_date_format="%Y%m%d",
)
