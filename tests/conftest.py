"""Shared test data and fixtures."""

from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Final

import pytest
from sqlalchemy import create_engine

from etl_example.load import SurveyDatabase, define_tables
from etl_example.transform import frame_to_records, transform_rows
from etl_example.validate import RowValidator

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

type RecordsFactory = Callable[
    [Sequence[Mapping[str, object]]], tuple[dict[str, object], ...]
]


@pytest.fixture
def raw_row() -> dict[str, object]:
    """A fresh copy of a valid raw row, safe to modify in a test."""
    return dict(VALID_RAW_ROW)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """URL of an empty SQLite database file in a temporary folder."""
    return f"sqlite:///{tmp_path / 'survey.db'}"


@pytest.fixture
def database(database_url: str) -> Iterator[SurveyDatabase]:
    """A survey database with the schema created."""
    engine = create_engine(database_url)
    survey_database = SurveyDatabase(engine, define_tables())
    survey_database.create_schema()

    yield survey_database

    engine.dispose()


@pytest.fixture
def make_records() -> RecordsFactory:
    """Turn valid raw rows into records ready to be stored."""

    def make(
        raw_rows: Sequence[Mapping[str, object]],
    ) -> tuple[dict[str, object], ...]:
        validation = RowValidator().validate(raw_rows)
        assert validation.invalid_rows == ()

        return frame_to_records(transform_rows(validation.valid_rows).frame)

    return make
