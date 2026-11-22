"""Loading respondents and keeping the wave summaries up to date.

Built on SQLAlchemy Core, so the same statements run on SQLite here
and on PostgreSQL (e.g. Supabase) by changing only the database URL.

The ``# SQL:`` comments show the plain SQL each SQLAlchemy statement
sends, for the column names of ``LAYOUT``. SQLAlchemy binds values as
parameters; the comments write them inline for readability.
"""

from collections.abc import Iterable, Mapping, Sequence
from itertools import groupby

from sqlalchemy import (
    Connection,
    Engine,
    RowMapping,
    delete,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

from survey_etl.layout import DataStatus
from survey_etl.storage.errors import (
    RespondentConflictError,
    SummaryNotFoundError,
    WaveNotFoundError,
)
from survey_etl.storage.queries import selected_summary_query, summary_query
from survey_etl.storage.reports import (
    AgeCategorySummary,
    BrandTotal,
    WaveSummary,
)
from survey_etl.storage.selections import AgeCategorySelection, WaveSelection
from survey_etl.storage.tables import SurveyTables

__all__ = ["SurveyDatabase"]


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

    def stored_respondent_ids(
        self, respondent_ids: Iterable[int]
    ) -> frozenset[int]:
        """Return which of the given respondent IDs are already stored.

        Args:
            respondent_ids: IDs to look up.

        Returns:
            The subset of the IDs found in the respondents table.
        """
        id_column = self._tables.respondents.c[
            self._tables.layout.columns.respondent_id
        ]
        # SQL (for IDs 1005 and 3001):
        #   SELECT respondent_id
        #   FROM respondents
        #   WHERE respondent_id IN (1005, 3001);
        query = select(id_column).where(id_column.in_(list(respondent_ids)))
        with self._engine.connect() as connection:
            return frozenset(connection.scalars(query))

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

        return self._wave_summary(wave, summary_rows)

    def read_summaries(
        self, waves: WaveSelection, age_categories: AgeCategorySelection
    ) -> tuple[WaveSummary, ...]:
        """Return the stored totals of the selected waves and ages.

        Args:
            waves: Waves to read.
            age_categories: Age categories to read, by position.

        Returns:
            One summary per wave found, oldest wave first, each with
            the selected categories, youngest first.

        Raises:
            InvalidSelectionError: If an age category position does
                not exist.
            SummaryNotFoundError: If no stored summary matches.
        """
        labels = age_categories.labels(self._tables.layout.age_categories)
        query = selected_summary_query(self._tables, waves, labels)
        with self._engine.connect() as connection:
            summary_rows = connection.execute(query).mappings().all()

        if not summary_rows:
            raise SummaryNotFoundError
        wave_column = self._tables.layout.columns.wave
        rows_by_wave = groupby(summary_rows, key=lambda row: row[wave_column])

        return tuple(
            self._wave_summary(wave, list(wave_rows))
            for wave, wave_rows in rows_by_wave
        )

    def _wave_summary(
        self, wave: int, summary_rows: Sequence[RowMapping]
    ) -> WaveSummary:
        """Build a wave's summary, youngest age category first."""
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
