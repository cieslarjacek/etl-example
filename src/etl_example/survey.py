"""Tracking-survey layout: columns, brands, age categories, statuses.

Every fact about the survey layout is declared once, in ``LAYOUT``.
The other modules receive a ``SurveyLayout`` and iterate over it
instead of repeating column names.
"""

import enum
from dataclasses import dataclass
from typing import Final

__all__ = [
    "LAYOUT",
    "AgeCategory",
    "AgeOutOfRangeError",
    "DataStatus",
    "SurveyLayout",
]


class DataStatus(enum.StrEnum):
    """Processing status of a stored respondent row."""

    NEW = "new"
    CURRENT = "current"


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
                f"age category {self.label!r}: minimum age must not be "
                f"negative, found {self.minimum_age}"
            )
        if self.maximum_age is not None and (
            self.maximum_age < self.minimum_age
        ):
            raise ValueError(
                f"age category {self.label!r}: maximum age "
                f"{self.maximum_age} is below minimum {self.minimum_age}"
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
class SurveyLayout:
    """Brands, age bands, date formats and column names of a survey.

    Attributes:
        brands: Brand identifiers, in reporting order.
        age_categories: Age bands, youngest first, without gaps.
        input_date_format: ``strptime`` format of incoming dates.
        storage_date_format: ``strftime`` format of stored dates.
        respondent_id: Column with the respondent identifier.
        interview_date: Column with the interview date.
        wave: Column with the wave number.
        birth_year: Column with the year of birth.
        age: Derived column with the age in the interview year.
        age_category: Derived column with the age category label.
        data_status: Column with the processing status.
    """

    brands: tuple[str, ...]
    age_categories: tuple[AgeCategory, ...]
    input_date_format: str
    storage_date_format: str
    respondent_id: str = "respondent_id"
    interview_date: str = "interview_date"
    wave: str = "wave"
    birth_year: str = "birth_year"
    age: str = "age"
    age_category: str = "age_category"
    data_status: str = "data_status"

    def __post_init__(self) -> None:
        """Validate the brands and the age bands.

        Raises:
            ValueError: If brands are missing or repeated, or the age
                bands are missing, unordered, overlapping or gapped.
        """
        if not self.brands or len(set(self.brands)) != len(self.brands):
            raise ValueError(
                f"brands must be non-empty and unique, found {self.brands}"
            )
        if not self.age_categories:
            raise ValueError("at least one age category is required")
        for younger, older in zip(
            self.age_categories, self.age_categories[1:], strict=False
        ):
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
            self.respondent_id,
            self.interview_date,
            self.wave,
            self.birth_year,
            *self.answer_columns,
        )

    @property
    def text_input_columns(self) -> frozenset[str]:
        """Input columns holding text; all the others hold integers."""
        return frozenset({self.interview_date})

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
    # Fieldwork exports write DD/MM/YYYY; storage uses YYYYMMDD.
    input_date_format="%d/%m/%Y",
    storage_date_format="%Y%m%d",
)
