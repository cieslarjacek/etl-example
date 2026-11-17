"""Definitions of the respondents and wave summary tables.

The ``# SQL:`` comments show the plain SQL each SQLAlchemy statement
sends, for the column names of ``LAYOUT``. SQLAlchemy binds values as
parameters; the comments write them inline for readability.
"""

from dataclasses import dataclass
from typing import Final

from sqlalchemy import Column, Integer, MetaData, String, Table

from etl_example.survey import LAYOUT, SurveyLayout

__all__ = [
    "TABLE_NAMES",
    "SurveyTables",
    "TableNames",
    "define_tables",
]


@dataclass(frozen=True, slots=True)
class TableNames:
    """Names of the tables and of the summary count columns.

    Attributes:
        respondents: Table with one row per respondent.
        wave_summary: Table with totals per wave and age category.
        respondents_total: Summary column counting respondents.
        total_suffix: Suffix turning an answer column into the
            summary column counting its 1 answers.
    """

    respondents: str = "respondents"
    wave_summary: str = "wave_summary"
    respondents_total: str = "respondents_total"
    total_suffix: str = "_total"

    def total_column(self, answer_column: str) -> str:
        """Return the summary column counting an answer column's 1s.

        Args:
            answer_column: Answer column, e.g. ``"brand2_usage"``.

        Returns:
            Summary column name, e.g. ``"brand2_usage_total"``.
        """
        return f"{answer_column}{self.total_suffix}"


TABLE_NAMES: Final = TableNames()


@dataclass(frozen=True, slots=True)
class SurveyTables:
    """Table definitions together with the names they were built from.

    Attributes:
        metadata: SQLAlchemy metadata holding both tables.
        respondents: Table with one row per respondent.
        wave_summary: Table with totals per wave and age category.
        layout: Survey layout declaring the columns.
        names: Table and summary column names.
    """

    metadata: MetaData
    respondents: Table
    wave_summary: Table
    layout: SurveyLayout
    names: TableNames


def _define_respondents(
    metadata: MetaData, layout: SurveyLayout, names: TableNames
) -> Table:
    """Define the table holding one row per respondent."""
    columns = layout.columns

    # SQL:
    #   CREATE TABLE respondents (
    #       respondent_id    INTEGER NOT NULL,
    #       interview_date   VARCHAR NOT NULL,
    #       wave             INTEGER NOT NULL,
    #       birth_year       INTEGER NOT NULL,
    #       age              INTEGER NOT NULL,
    #       age_category     VARCHAR NOT NULL,
    #       brand1_awareness INTEGER,
    #       brand2_awareness INTEGER,
    #       brand3_awareness INTEGER,
    #       brand1_usage     INTEGER,
    #       brand2_usage     INTEGER,
    #       brand3_usage     INTEGER,
    #       data_status      VARCHAR NOT NULL,
    #       PRIMARY KEY (respondent_id)
    #   );
    #   CREATE INDEX ix_respondents_wave ON respondents (wave);
    #   CREATE INDEX ix_respondents_data_status
    #       ON respondents (data_status);
    return Table(
        names.respondents,
        metadata,
        Column(columns.respondent_id, Integer, primary_key=True),
        Column(columns.interview_date, String, nullable=False),
        Column(columns.wave, Integer, nullable=False, index=True),
        Column(columns.birth_year, Integer, nullable=False),
        Column(columns.age, Integer, nullable=False),
        Column(columns.age_category, String, nullable=False),
        *(Column(column, Integer) for column in layout.answer_columns),
        Column(columns.data_status, String, nullable=False, index=True),
    )


def _define_wave_summary(
    metadata: MetaData, layout: SurveyLayout, names: TableNames
) -> Table:
    """Define the table holding totals per wave and age category."""
    # SQL:
    #   CREATE TABLE wave_summary (
    #       wave                   INTEGER NOT NULL,
    #       age_category           VARCHAR NOT NULL,
    #       respondents_total      INTEGER NOT NULL,
    #       brand1_awareness_total INTEGER NOT NULL,
    #       brand2_awareness_total INTEGER NOT NULL,
    #       brand3_awareness_total INTEGER NOT NULL,
    #       brand1_usage_total     INTEGER NOT NULL,
    #       brand2_usage_total     INTEGER NOT NULL,
    #       brand3_usage_total     INTEGER NOT NULL,
    #       PRIMARY KEY (wave, age_category)
    #   );
    return Table(
        names.wave_summary,
        metadata,
        Column(layout.columns.wave, Integer, primary_key=True),
        Column(layout.columns.age_category, String, primary_key=True),
        Column(names.respondents_total, Integer, nullable=False),
        *(
            Column(names.total_column(column), Integer, nullable=False)
            for column in layout.answer_columns
        ),
    )


def define_tables(
    layout: SurveyLayout = LAYOUT, names: TableNames = TABLE_NAMES
) -> SurveyTables:
    """Define the respondents and wave summary tables.

    Args:
        layout: Survey layout declaring the columns.
        names: Table and summary column names.

    Returns:
        Both tables, sharing one metadata object.
    """
    metadata = MetaData()

    return SurveyTables(
        metadata,
        _define_respondents(metadata, layout, names),
        _define_wave_summary(metadata, layout, names),
        layout,
        names,
    )
