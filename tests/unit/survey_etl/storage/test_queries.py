from sqlalchemy.dialects.postgresql.base import PGDialect

from survey_etl.storage import (
    WaveSelection,
    define_tables,
    selected_summary_query,
    summary_query,
)


def test_summary_query_compiles_for_postgresql() -> None:
    query = summary_query(define_tables(), [2, 3])
    # SQLAlchemy ships its dialect classes without type hints.
    dialect = PGDialect()  # type: ignore[no-untyped-call]

    sql = str(query.compile(dialect=dialect))

    assert "count(*) AS respondents_total" in sql
    assert "GROUP BY respondents.wave, respondents.age_category" in sql


def test_latest_waves_query_compiles_for_postgresql() -> None:
    query = selected_summary_query(
        define_tables(), WaveSelection(latest_count=2), ["18-24"]
    )
    dialect = PGDialect()  # type: ignore[no-untyped-call]

    sql = str(query.compile(dialect=dialect))

    assert "ORDER BY wave_summary.wave DESC" in sql
    assert "LIMIT" in sql
