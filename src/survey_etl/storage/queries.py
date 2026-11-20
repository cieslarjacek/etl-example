"""Queries counting answers per wave and reading the stored summaries.

The ``# SQL:`` comments show the plain SQL each SQLAlchemy statement
sends, for the column names of ``LAYOUT``. SQLAlchemy binds values as
parameters; the comments write them inline for readability.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Column, ColumnElement, Select, select, true
from sqlalchemy import func as sql_functions

from survey_etl.storage.selections import WaveSelection
from survey_etl.storage.tables import SurveyTables

__all__ = ["selected_summary_query", "summary_query"]


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


def _wave_condition(
    wave: Column[Any], selection: WaveSelection
) -> ColumnElement[bool]:
    """Build the WHERE condition for the selected waves."""
    if selection.number is not None:
        return wave == selection.number
    if selection.latest_count is not None:
        latest_waves = (
            select(wave)
            .distinct()
            .order_by(wave.desc())
            .limit(selection.latest_count)
        )
        return wave.in_(latest_waves.scalar_subquery())
    condition: ColumnElement[bool] = true()
    if selection.start is not None:
        condition = condition & (wave >= selection.start)
    if selection.end is not None:
        condition = condition & (wave <= selection.end)

    return condition


def selected_summary_query(
    tables: SurveyTables,
    waves: WaveSelection,
    age_category_labels: Sequence[str],
) -> Select[*tuple[Any, ...]]:
    """Build the query reading stored summaries of a selection.

    Args:
        tables: Survey table definitions.
        waves: Waves to read.
        age_category_labels: Labels of the age categories to read.

    Returns:
        A SELECT of summary rows, ordered by wave.
    """
    summary = tables.wave_summary
    wave = summary.c[tables.layout.columns.wave]
    age_category = summary.c[tables.layout.columns.age_category]

    # SQL (wave_last=2, agecat_from=1, agecat_to=2):
    #   SELECT
    #       wave, age_category, respondents_total,
    #       brand1_awareness_total, brand2_awareness_total,
    #       brand3_awareness_total, brand1_usage_total,
    #       brand2_usage_total, brand3_usage_total
    #   FROM wave_summary
    #   WHERE wave IN (
    #           SELECT DISTINCT wave
    #           FROM wave_summary
    #           ORDER BY wave DESC
    #           LIMIT 2
    #       )
    #       AND age_category IN ('18-24', '25-34')
    #   ORDER BY wave;
    # The wave condition is instead "wave = 3" for wave=3, and
    # "wave >= 2 AND wave <= 3" for wave_from=2 and wave_to=3.
    return (
        select(summary)
        .where(_wave_condition(wave, waves))
        .where(age_category.in_(age_category_labels))
        .order_by(wave)
    )
