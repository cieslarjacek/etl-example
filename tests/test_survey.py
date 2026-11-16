import pickle

import pytest

from etl_example.survey import (
    LAYOUT,
    AgeCategory,
    AgeOutOfRangeError,
    SurveyLayout,
)

ADJACENT_CATEGORIES = (AgeCategory("18-29", 18, 29), AgeCategory("30+", 30))


@pytest.mark.parametrize(
    ("age", "label"),
    [
        (18, "18-24"),
        (24, "18-24"),
        (25, "25-34"),
        (54, "45-54"),
        (55, "55+"),
        (99, "55+"),
    ],
)
def test_age_maps_to_category_at_band_boundaries(age: int, label: str) -> None:
    assert LAYOUT.age_category_label(age) == label


def test_age_below_youngest_category_is_an_error() -> None:
    with pytest.raises(AgeOutOfRangeError, match="age 17"):
        LAYOUT.age_category_label(17)


def test_age_out_of_range_error_survives_pickling() -> None:
    restored = pickle.loads(pickle.dumps(AgeOutOfRangeError(17)))  # noqa: S301

    assert str(restored) == "no age category contains age 17"


def test_minimum_age_is_lower_bound_of_youngest_category() -> None:
    assert LAYOUT.minimum_age == 18


def test_answer_columns_list_awareness_before_usage() -> None:
    assert LAYOUT.answer_columns == (
        "brand1_awareness",
        "brand2_awareness",
        "brand3_awareness",
        "brand1_usage",
        "brand2_usage",
        "brand3_usage",
    )


def test_input_columns_start_with_respondent_fields() -> None:
    assert LAYOUT.input_columns[:4] == (
        "respondent_id",
        "interview_date",
        "wave",
        "birth_year",
    )


def test_layout_rejects_repeated_brands() -> None:
    with pytest.raises(ValueError, match="unique"):
        SurveyLayout(("a", "a"), ADJACENT_CATEGORIES, "%d", "%d")


def test_layout_rejects_missing_brands() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        SurveyLayout((), ADJACENT_CATEGORIES, "%d", "%d")


def test_layout_rejects_missing_age_categories() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        SurveyLayout(("a",), (), "%d", "%d")


def test_layout_rejects_gap_between_age_categories() -> None:
    gapped = (AgeCategory("18-29", 18, 29), AgeCategory("31+", 31))

    with pytest.raises(ValueError, match="adjacent"):
        SurveyLayout(("a",), gapped, "%d", "%d")


def test_layout_rejects_open_band_before_last_category() -> None:
    open_first = (AgeCategory("18+", 18), AgeCategory("30+", 30))

    with pytest.raises(ValueError, match="adjacent"):
        SurveyLayout(("a",), open_first, "%d", "%d")


def test_age_category_rejects_negative_minimum() -> None:
    with pytest.raises(ValueError, match="negative"):
        AgeCategory("x", -1, 5)


def test_age_category_rejects_maximum_below_minimum() -> None:
    with pytest.raises(ValueError, match="below 'minimum_age'"):
        AgeCategory("x", 30, 20)
