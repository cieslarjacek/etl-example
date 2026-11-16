import pickle

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql.base import PGDialect

from conftest import RecordsFactory
from etl_example.database import (
    RespondentConflictError,
    SurveyDatabase,
    WaveNotFoundError,
    define_tables,
    summary_query,
)
from etl_example.reports import BrandTotal


def rows_for_wave(
    raw_row: dict[str, object], wave: int, respondent_ids: range
) -> list[dict[str, object]]:
    """Copies of a raw row for one wave, one per respondent ID."""
    return [
        raw_row | {"wave": wave, "respondent_id": respondent_id}
        for respondent_id in respondent_ids
    ]


def test_loaded_rows_are_marked_current(
    database: SurveyDatabase,
    database_url: str,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(make_records([raw_row]))

    status = define_tables().respondents.c["data_status"]
    engine = create_engine(database_url)
    with engine.connect() as connection:
        statuses = connection.scalars(select(status)).all()
    engine.dispose()
    assert statuses == ["current"]


def test_summary_counts_respondents_and_answers(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    unaware_row = raw_row | {
        "respondent_id": 3002,
        "brand1_awareness": 0,
        "brand1_usage": 0,
    }
    database.load_new_respondents(make_records([raw_row, unaware_row]))

    summary = database.read_wave_summary(3)

    category = summary.age_categories[0]
    assert category.age_category == "35-44"
    assert category.respondents_total == 2
    assert category.brands[0] == BrandTotal("brand1", 1, 1)
    assert category.brands[1] == BrandTotal("brand2", 2, 0)


def test_unanswered_questions_are_not_counted(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    raw_row |= {"brand1_awareness": None, "brand1_usage": None}
    database.load_new_respondents(make_records([raw_row]))

    summary = database.read_wave_summary(3)

    assert summary.age_categories[0].brands[0] == BrandTotal("brand1", 0, 0)


def test_age_categories_are_ordered_youngest_first(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    rows = [
        raw_row | {"respondent_id": 1, "birth_year": 1950},
        raw_row | {"respondent_id": 2, "birth_year": 2000},
        raw_row | {"respondent_id": 3, "birth_year": 1990},
    ]
    database.load_new_respondents(make_records(rows))

    summary = database.read_wave_summary(3)

    labels = [category.age_category for category in summary.age_categories]
    assert labels == ["25-34", "35-44", "55+"]


def test_late_row_refreshes_its_earlier_wave(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(
        make_records(rows_for_wave(raw_row, 2, range(1, 3)))
    )

    database.load_new_respondents(
        make_records(rows_for_wave(raw_row, 2, range(3, 4)))
    )

    summary = database.read_wave_summary(2)
    assert summary.age_categories[0].respondents_total == 3


def test_load_leaves_other_waves_untouched(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(
        make_records(rows_for_wave(raw_row, 1, range(1, 3)))
    )

    database.load_new_respondents(
        make_records(rows_for_wave(raw_row, 2, range(3, 4)))
    )

    summary = database.read_wave_summary(1)
    assert summary.age_categories[0].respondents_total == 2


def test_empty_load_keeps_summaries_unchanged(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(make_records([raw_row]))
    summary_before = database.read_wave_summary(3)

    database.load_new_respondents(())

    assert database.read_wave_summary(3) == summary_before


def test_stored_respondent_ids_returns_known_subset(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(make_records([raw_row]))

    stored_ids = database.stored_respondent_ids([3001, 9999])

    assert stored_ids == frozenset({3001})


def test_stored_respondent_ids_of_no_ids_is_empty(
    database: SurveyDatabase,
) -> None:
    assert database.stored_respondent_ids([]) == frozenset()


def test_unknown_wave_is_not_found(database: SurveyDatabase) -> None:
    with pytest.raises(WaveNotFoundError, match="wave 7"):
        database.read_wave_summary(7)


def test_storing_an_id_twice_is_a_conflict(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    records = make_records([raw_row])
    database.load_new_respondents(records)

    with pytest.raises(RespondentConflictError, match="concurrent batch"):
        database.load_new_respondents(records)


def test_failed_load_stores_nothing(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(make_records([raw_row]))
    new_row = raw_row | {"respondent_id": 3002}

    with pytest.raises(RespondentConflictError):
        database.load_new_respondents(make_records([new_row, raw_row]))

    assert database.stored_respondent_ids([3002]) == frozenset()


def test_summary_query_is_portable_to_postgresql() -> None:
    query = summary_query(define_tables(), [2, 3])
    # SQLAlchemy ships its dialect classes without type hints.
    dialect = PGDialect()  # type: ignore[no-untyped-call]

    sql = str(query.compile(dialect=dialect))

    assert "count(*) AS respondents_total" in sql
    assert "GROUP BY respondents.wave, respondents.age_category" in sql


@pytest.mark.parametrize(
    "error",
    [WaveNotFoundError(7), RespondentConflictError("UNIQUE failed")],
)
def test_database_errors_survive_pickling(error: Exception) -> None:
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - own data

    assert str(restored) == str(error)
