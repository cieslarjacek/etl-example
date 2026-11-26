import pytest

from survey_etl.transform import CorrectedValue, CorrectionReason


def test_corrected_value_cannot_be_changed() -> None:
    value = CorrectedValue(
        3, 3003, "brand3_usage", 1, 0, CorrectionReason.USAGE_WITHOUT_AWARENESS
    )

    with pytest.raises(AttributeError):
        value.corrected = 1  # type: ignore[misc]
