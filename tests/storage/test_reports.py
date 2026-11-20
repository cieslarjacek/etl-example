import pytest

from survey_etl.storage import (
    AgeCategorySummary,
    BrandTotal,
    WaveSummary,
)


def test_wave_summary_cannot_be_changed() -> None:
    category = AgeCategorySummary("18-24", 2, (BrandTotal("brand1", 2, 1),))
    summary = WaveSummary(3, (category,))

    with pytest.raises(AttributeError):
        summary.wave = 4  # type: ignore[misc]
