import pytest
from sqlalchemy import create_engine, select

from survey_etl.storage import (
    AgeCategorySelection,
    BrandTotal,
    RespondentConflictError,
    SummaryNotFoundError,
    SurveyDatabase,
    WaveNotFoundError,
    WaveSelection,
    define_tables,
)
from tests.survey_etl.conftest import RecordsFactory


def rows_for_wave(
    raw_row: dict[str, object], wave: int, respondent_ids: range
) -> list[dict[str, object]]:
    """Copies of a raw row for one wave, one per respondent ID."""
    return [
        raw_row | {"wave": wave, "respondent_id": respondent_id}
        for respondent_id in respondent_ids
    ]


# ---- load_new_respondents ----


def test_loaded_rows_are_tagged_current(
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


def test_storing_an_id_twice_is_a_conflict(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    records = make_records([raw_row])
    database.load_new_respondents(records)

    with pytest.raises(RespondentConflictError, match="already stored"):
        database.load_new_respondents(records)


def test_conflicting_load_stores_nothing(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(make_records([raw_row]))
    summary_before = database.read_wave_summary(3)
    new_row = raw_row | {"respondent_id": 3002}

    with pytest.raises(RespondentConflictError):
        database.load_new_respondents(make_records([new_row, raw_row]))

    assert database.read_wave_summary(3) == summary_before


# ---- stored_respondent_ids ----


def test_stored_respondent_ids_returns_known_subset(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    database.load_new_respondents(make_records([raw_row]))

    stored_ids = database.stored_respondent_ids([3001, 9999])

    assert stored_ids == frozenset({3001})


def test_stored_respondent_ids_of_no_ids_are_empty(
    database: SurveyDatabase,
) -> None:
    assert database.stored_respondent_ids([]) == frozenset()


# ---- read_wave_summary ----


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
    assert category.brands == (
        BrandTotal("brand1", 1, 1),
        BrandTotal("brand2", 2, 0),
        BrandTotal("brand3", 0, 0),
    )


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


def test_unknown_wave_is_not_found(database: SurveyDatabase) -> None:
    with pytest.raises(WaveNotFoundError, match="wave 7"):
        database.read_wave_summary(7)


# ---- read_summaries ----


def load_three_waves(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    """Store waves 1 to 3, each with respondents aged 22 and 36."""
    rows = [
        raw_row
        | {"wave": wave, "respondent_id": wave * 10 + offset}
        | {"birth_year": birth_year}
        for wave in (1, 2, 3)
        for offset, birth_year in ((1, 2004), (2, 1990))
    ]
    database.load_new_respondents(make_records(rows))


def summarised_waves(
    database: SurveyDatabase,
    waves: WaveSelection,
    age_categories: AgeCategorySelection,
) -> list[tuple[int, list[str]]]:
    """Read summaries and keep each wave with its category labels."""
    return [
        (
            summary.wave,
            [category.age_category for category in summary.age_categories],
        )
        for summary in database.read_summaries(waves, age_categories)
    ]


@pytest.mark.parametrize(
    ("waves", "expected_waves"),
    [
        (WaveSelection(), [1, 2, 3]),
        (WaveSelection(number=2), [2]),
        (WaveSelection(latest_count=2), [2, 3]),
        (WaveSelection(start=2), [2, 3]),
        (WaveSelection(end=2), [1, 2]),
        (WaveSelection(start=1, end=2), [1, 2]),
    ],
)
def test_read_summaries_selects_waves(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
    waves: WaveSelection,
    expected_waves: list[int],
) -> None:
    load_three_waves(database, raw_row, make_records)

    summaries = summarised_waves(database, waves, AgeCategorySelection())

    assert [wave for wave, _ in summaries] == expected_waves


@pytest.mark.parametrize(
    ("age_categories", "expected_labels"),
    [
        (AgeCategorySelection(), ["18-24", "35-44"]),
        (AgeCategorySelection(number=3), ["35-44"]),
        (AgeCategorySelection(start=1, end=2), ["18-24"]),
    ],
)
def test_read_summaries_selects_age_categories(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
    age_categories: AgeCategorySelection,
    expected_labels: list[str],
) -> None:
    load_three_waves(database, raw_row, make_records)

    summaries = summarised_waves(
        database, WaveSelection(number=3), age_categories
    )

    assert summaries == [(3, expected_labels)]


def test_read_summaries_without_match_is_not_found(
    database: SurveyDatabase,
    raw_row: dict[str, object],
    make_records: RecordsFactory,
) -> None:
    load_three_waves(database, raw_row, make_records)

    with pytest.raises(SummaryNotFoundError):
        database.read_summaries(
            WaveSelection(number=3), AgeCategorySelection(number=5)
        )


def test_read_summaries_of_empty_database_is_not_found(
    database: SurveyDatabase,
) -> None:
    with pytest.raises(SummaryNotFoundError):
        database.read_summaries(WaveSelection(), AgeCategorySelection())
