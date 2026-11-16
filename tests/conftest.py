"""Shared test data and fixtures."""

from types import MappingProxyType
from typing import Final

import pytest

VALID_RAW_ROW: Final = MappingProxyType(
    {
        "respondent_id": 3001,
        "interview_date": "15/09/2026",
        "wave": 3,
        "birth_year": 1990,
        "brand1_awareness": 1,
        "brand2_awareness": 1,
        "brand3_awareness": 0,
        "brand1_usage": 1,
        "brand2_usage": 0,
        "brand3_usage": 0,
    }
)


@pytest.fixture
def raw_row() -> dict[str, object]:
    """A fresh copy of a valid raw row, safe to modify in a test."""
    return dict(VALID_RAW_ROW)
