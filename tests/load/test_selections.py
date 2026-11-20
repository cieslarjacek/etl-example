import pytest

from etl_example.load import (
    AgeCategorySelection,
    InvalidSelectionError,
    WaveSelection,
)
from etl_example.survey import LAYOUT

CATEGORIES = LAYOUT.age_categories


# ---- WaveSelection ----


@pytest.mark.parametrize(
    "selection",
    [
        WaveSelection(),
        WaveSelection(number=3),
        WaveSelection(latest_count=2),
        WaveSelection(start=2),
        WaveSelection(end=3),
        WaveSelection(start=2, end=2),
    ],
)
def test_wave_selection_accepts_one_form(selection: WaveSelection) -> None:
    assert isinstance(selection, WaveSelection)


@pytest.mark.parametrize(
    "fields",
    [
        {"number": 3, "latest_count": 2},
        {"number": 3, "start": 2},
        {"latest_count": 2, "end": 3},
    ],
)
def test_wave_selection_rejects_several_forms(fields: dict[str, int]) -> None:
    with pytest.raises(InvalidSelectionError, match="one way only"):
        WaveSelection(**fields)


def test_wave_selection_rejects_reversed_range() -> None:
    with pytest.raises(
        InvalidSelectionError, match="range starts at 3, after its end 2"
    ):
        WaveSelection(start=3, end=2)


def test_wave_selection_rejects_number_below_one() -> None:
    with pytest.raises(InvalidSelectionError, match="found 0"):
        WaveSelection(latest_count=0)


# ---- AgeCategorySelection ----


def test_no_age_category_selects_all() -> None:
    labels = AgeCategorySelection().labels(CATEGORIES)

    assert labels == ("18-24", "25-34", "35-44", "45-54", "55+")


def test_single_age_category_by_position() -> None:
    assert AgeCategorySelection(number=2).labels(CATEGORIES) == ("25-34",)


def test_age_category_range_includes_both_ends() -> None:
    labels = AgeCategorySelection(start=2, end=4).labels(CATEGORIES)

    assert labels == ("25-34", "35-44", "45-54")


def test_open_age_category_range_runs_to_the_oldest() -> None:
    labels = AgeCategorySelection(start=4).labels(CATEGORIES)

    assert labels == ("45-54", "55+")


def test_open_age_category_range_starts_at_the_youngest() -> None:
    labels = AgeCategorySelection(end=2).labels(CATEGORIES)

    assert labels == ("18-24", "25-34")


@pytest.mark.parametrize(
    "selection",
    [AgeCategorySelection(number=6), AgeCategorySelection(start=2, end=6)],
)
def test_age_category_beyond_the_last_is_rejected(
    selection: AgeCategorySelection,
) -> None:
    with pytest.raises(
        InvalidSelectionError, match="age category 6 does not exist"
    ):
        selection.labels(CATEGORIES)


def test_age_category_selection_rejects_both_forms() -> None:
    with pytest.raises(InvalidSelectionError, match="one way only"):
        AgeCategorySelection(number=2, end=3)


def test_age_category_selection_rejects_reversed_range() -> None:
    with pytest.raises(InvalidSelectionError, match="after its end"):
        AgeCategorySelection(start=4, end=1)


def test_age_category_selection_rejects_position_below_one() -> None:
    with pytest.raises(InvalidSelectionError, match="start at 1"):
        AgeCategorySelection(start=0)
