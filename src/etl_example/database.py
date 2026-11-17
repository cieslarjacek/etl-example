"""SQL storage of respondents and per-wave summaries.

Built on SQLAlchemy Core, so the same statements run on SQLite here
and on PostgreSQL (e.g. Supabase) by changing only the database URL.

The ``# SQL:`` comments show the plain SQL each SQLAlchemy statement
sends, for the column names of ``LAYOUT``. SQLAlchemy binds values as
parameters; the comments write them inline for readability.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import (
    Column,
    Connection,
    Engine,
    Integer,
    MetaData,
    RowMapping,
    Select,
    String,
    Table,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy import func as sql_functions
from sqlalchemy.exc import IntegrityError

from etl_example.summary_reports import (
    AgeCategorySummary,
    BrandTotal,
    WaveSummary,
)
from etl_example.survey_layout import LAYOUT, DataStatus, SurveyLayout

__all__ = [
    "TABLE_NAMES",
    "RespondentConflictError",
    "SurveyDatabase",
    "SurveyTables",
    "TableNames",
    "WaveNotFoundError",
    "define_tables",
    "summary_query",
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


class WaveNotFoundError(LookupError):
    """No summary is stored for the requested wave."""

    def __init__(self, wave: int) -> None:
        """Store the wave that was requested.

        Args:
            wave: Wave number.
        """
        super().__init__(wave)
        self.wave = wave

    def __str__(self) -> str:
        """Name the missing wave."""
        return f"no summary stored for wave {self.wave}"


class RespondentConflictError(RuntimeError):
    """A respondent ID being stored is already in the database."""

    def __init__(self, database_message: str) -> None:
        """Store the database's description of the conflict.

        Args:
            database_message: Message of the database driver.
        """
        super().__init__(database_message)
        self.database_message = database_message

    def __str__(self) -> str:
        """Explain the conflict and what was stored."""
        return (
            "respondent ID already stored, nothing from this batch was "
            f"saved ({self.database_message})"
        )


class SurveyDatabase:
    """Stores respondents and keeps the wave summaries up to date."""

    def __init__(self, engine: Engine, tables: SurveyTables) -> None:
        """Store the engine and the table definitions.

        Args:
            engine: SQLAlchemy engine of the target database.
            tables: Survey table definitions.
        """
        self._engine = engine
        self._tables = tables

    def create_schema(self) -> None:
        """Create the tables that do not exist yet."""
        # SQL: both CREATE TABLE statements above, each with
        # IF NOT EXISTS (SQLAlchemy checks for the table first).
        self._tables.metadata.create_all(self._engine)

    def load_new_respondents(
        self, records: Sequence[Mapping[str, object]]
    ) -> None:
        """Store new rows, refresh their summaries, mark rows current.

        Every wave holding rows tagged ``new`` gets its summary rebuilt
        from all its rows; then those rows are tagged ``current``. All
        steps run in one transaction: on failure nothing is stored.

        Args:
            records: Respondent rows tagged ``new``.

        Raises:
            RespondentConflictError: If a respondent ID is already
                stored.
        """
        # SQL (one transaction; the helpers show their own statements):
        #   BEGIN;
        #   INSERT INTO respondents (
        #       respondent_id, interview_date, wave, birth_year, age,
        #       age_category, brand1_awareness, brand2_awareness,
        #       brand3_awareness, brand1_usage, brand2_usage,
        #       brand3_usage, data_status
        #   ) VALUES
        #       (3001, '20260915', 3, 1990, 36, '35-44',
        #        1, 1, 0, 1, 0, 0, 'new'),
        #       ...;                                -- one per record
        #   -- _waves_with_new_rows, _replace_wave_summaries,
        #   -- _mark_rows_current
        #   COMMIT;                     -- ROLLBACK on any error
        try:
            with self._engine.begin() as connection:
                if records:
                    connection.execute(
                        insert(self._tables.respondents), list(records)
                    )
                waves = _waves_with_new_rows(connection, self._tables)
                _replace_wave_summaries(connection, self._tables, waves)
                _mark_rows_current(connection, self._tables)
        except IntegrityError as error:
            raise RespondentConflictError(str(error.orig)) from error

    def read_wave_summary(self, wave: int) -> WaveSummary:
        """Return the stored totals of a wave per age category.

        Args:
            wave: Wave number.

        Returns:
            The wave's totals, youngest age category first.

        Raises:
            WaveNotFoundError: If no summary is stored for the wave.
        """
        summary = self._tables.wave_summary
        # SQL (for wave 3):
        #   SELECT
        #       wave, age_category, respondents_total,
        #       brand1_awareness_total, brand2_awareness_total,
        #       brand3_awareness_total, brand1_usage_total,
        #       brand2_usage_total, brand3_usage_total
        #   FROM wave_summary
        #   WHERE wave = 3;
        query = select(summary).where(
            summary.c[self._tables.layout.columns.wave] == wave
        )
        with self._engine.connect() as connection:
            summary_rows = connection.execute(query).mappings().all()

        if not summary_rows:
            raise WaveNotFoundError(wave)
        categories = map(self._category_summary, summary_rows)

        return WaveSummary(wave, tuple(sorted(categories, key=self._age_rank)))

    def _category_summary(self, row: RowMapping) -> AgeCategorySummary:
        """Convert one summary row to a value object."""
        layout = self._tables.layout
        names = self._tables.names
        brands = tuple(
            BrandTotal(
                brand,
                row[names.total_column(layout.awareness_column(brand))],
                row[names.total_column(layout.usage_column(brand))],
            )
            for brand in layout.brands
        )

        return AgeCategorySummary(
            row[layout.columns.age_category],
            row[names.respondents_total],
            brands,
        )

    def _age_rank(self, category_summary: AgeCategorySummary) -> int:
        """Sort key placing age categories youngest first."""
        labels = [
            category.label for category in self._tables.layout.age_categories
        ]

        return labels.index(category_summary.age_category)


def _waves_with_new_rows(
    connection: Connection, tables: SurveyTables
) -> tuple[int, ...]:
    """Return the waves holding rows tagged ``new``."""
    wave = tables.respondents.c[tables.layout.columns.wave]
    status = tables.respondents.c[tables.layout.columns.data_status]
    # SQL:
    #   SELECT DISTINCT wave
    #   FROM respondents
    #   WHERE data_status = 'new'
    #   ORDER BY wave;
    query = (
        select(wave)
        .distinct()
        .where(status == DataStatus.NEW.value)
        .order_by(wave)
    )

    return tuple(connection.scalars(query))


def _replace_wave_summaries(
    connection: Connection, tables: SurveyTables, waves: Sequence[int]
) -> None:
    """Rebuild the summary rows of the given waves."""
    if not waves:
        return
    summary = tables.wave_summary
    # SQL (for waves 2 and 3):
    #   DELETE FROM wave_summary WHERE wave IN (2, 3);
    connection.execute(
        delete(summary).where(summary.c[tables.layout.columns.wave].in_(waves))
    )
    query = summary_query(tables, waves)
    # SQL (for waves 2 and 3):
    #   INSERT INTO wave_summary (
    #       wave, age_category, respondents_total,
    #       brand1_awareness_total, brand2_awareness_total,
    #       brand3_awareness_total, brand1_usage_total,
    #       brand2_usage_total, brand3_usage_total
    #   )
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
    connection.execute(
        insert(summary).from_select(list(query.selected_columns.keys()), query)
    )


def _mark_rows_current(connection: Connection, tables: SurveyTables) -> None:
    """Tag every ``new`` row as ``current``."""
    status = tables.respondents.c[tables.layout.columns.data_status]
    # SQL:
    #   UPDATE respondents SET data_status = 'current'
    #   WHERE data_status = 'new';
    connection.execute(
        update(tables.respondents)
        .where(status == DataStatus.NEW.value)
        .values({status: DataStatus.CURRENT.value})
    )
