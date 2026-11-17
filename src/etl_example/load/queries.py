"""The query counting respondents and answers per wave.

The ``# SQL:`` comments show the plain SQL each SQLAlchemy statement
sends, for the column names of ``LAYOUT``. SQLAlchemy binds values as
parameters; the comments write them inline for readability.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy import func as sql_functions

from etl_example.load.tables import SurveyTables

__all__ = ["summary_query"]


def summary_query(
    tables: SurveyTables, waves: Sequence[int]
) -> Select[*tuple[Any, ...]]:
    """Build the query counting respondents and answers per wave.

    ``SUM`` of a 0/1 column counts its 1 answers; unanswered questions
    are NULL and ``SUM`` skips them. ``COALESCE`` turns the NULL sum of
    a group without any answer into 0.

    Args:
        tables: Survey table definitions.
        waves: Waves to summarise.

    Returns:
        A SELECT with one row per wave and age category.
    """
    respondents = tables.respondents
    wave = respondents.c[tables.layout.columns.wave]
    age_category = respondents.c[tables.layout.columns.age_category]
    answer_totals = (
        sql_functions.coalesce(
            sql_functions.sum(respondents.c[column]), 0
        ).label(tables.names.total_column(column))
        for column in tables.layout.answer_columns
    )

    # SQL (for waves 2 and 3):
    #   SELECT
    #       wave,
    #       age_category,
    #       COUNT(*) AS respondents_total,
    #       COALESCE(SUM(brand1_awareness), 0)
    #           AS brand1_awareness_total,
    #       COALESCE(SUM(brand2_awareness), 0)
    #           AS brand2_awareness_total,
    #       COALESCE(SUM(brand3_awareness), 0)
    #           AS brand3_awareness_total,
    #       COALESCE(SUM(brand1_usage), 0)
    #           AS brand1_usage_total,
    #       COALESCE(SUM(brand2_usage), 0)
    #           AS brand2_usage_total,
    #       COALESCE(SUM(brand3_usage), 0)
    #           AS brand3_usage_total
    #   FROM respondents
    #   WHERE wave IN (2, 3)
    #   GROUP BY wave, age_category;
    return (
        select(
            wave,
            age_category,
            sql_functions.count().label(tables.names.respondents_total),
            *answer_totals,
        )
        .where(wave.in_(waves))
        .group_by(wave, age_category)
    )
