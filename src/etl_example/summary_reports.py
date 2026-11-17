"""Wave totals per age category, reported back to the client."""

from dataclasses import dataclass

__all__ = [
    "AgeCategorySummary",
    "BrandTotal",
    "WaveSummary",
]


@dataclass(frozen=True, slots=True)
class BrandTotal:
    """Awareness and usage counts of one brand.

    Attributes:
        brand: Brand identifier.
        awareness_total: Respondents aware of the brand.
        usage_total: Respondents using the brand.
    """

    brand: str
    awareness_total: int
    usage_total: int


@dataclass(frozen=True, slots=True)
class AgeCategorySummary:
    """Wave totals for one age category.

    Attributes:
        age_category: Age category label.
        respondents_total: Respondents in the category.
        brands: Awareness and usage counts per brand.
    """

    age_category: str
    respondents_total: int
    brands: tuple[BrandTotal, ...]


@dataclass(frozen=True, slots=True)
class WaveSummary:
    """Totals of one wave, broken down by age category.

    Attributes:
        wave: Wave number.
        age_categories: Totals per age category, youngest first.
    """

    wave: int
    age_categories: tuple[AgeCategorySummary, ...]
