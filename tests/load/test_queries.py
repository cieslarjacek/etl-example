from sqlalchemy.dialects.postgresql.base import PGDialect

from etl_example.load import (
    define_tables,
    summary_query,
)


def test_summary_query_compiles_for_postgresql() -> None:
    query = summary_query(define_tables(), [2, 3])
    # SQLAlchemy ships its dialect classes without type hints.
    dialect = PGDialect()  # type: ignore[no-untyped-call]

    sql = str(query.compile(dialect=dialect))

    assert "count(*) AS respondents_total" in sql
    assert "GROUP BY respondents.wave, respondents.age_category" in sql
