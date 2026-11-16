import json
import pickle
from pathlib import Path

import pytest

from etl_example.survey_csv import (
    CsvHeaderError,
    CsvRowLengthError,
    parse_survey_csv,
    to_batch_json,
)

HEADER = (
    "respondent_id,interview_date,wave,birth_year,brand1_awareness,"
    "brand2_awareness,brand3_awareness,brand1_usage,brand2_usage,brand3_usage"
)


def test_integers_are_converted_and_dates_kept_as_text() -> None:
    text = f"{HEADER}\n3001,07/09/2026,3,2005,1,1,0,1,0,0\n"

    rows = parse_survey_csv(text, "wave3.csv")

    assert rows[0]["respondent_id"] == 3001
    assert rows[0]["interview_date"] == "07/09/2026"
    assert rows[0]["brand3_usage"] == 0


def test_empty_cells_become_none() -> None:
    text = f"{HEADER}\n3001,07/09/2026,3,2005,1,,0,1, ,0\n"

    rows = parse_survey_csv(text, "wave3.csv")

    assert rows[0]["brand2_awareness"] is None
    assert rows[0]["brand2_usage"] is None


def test_non_integer_value_is_passed_on_as_text() -> None:
    text = f"{HEADER}\n3001,07/09/2026,3,2005,yes,1,0,1,0,0\n"

    rows = parse_survey_csv(text, "wave3.csv")

    assert rows[0]["brand1_awareness"] == "yes"


def test_header_only_file_has_no_rows() -> None:
    assert parse_survey_csv(f"{HEADER}\n", "wave3.csv") == []


def test_reordered_header_is_an_error() -> None:
    columns = HEADER.split(",")
    columns[0], columns[2] = columns[2], columns[0]

    with pytest.raises(CsvHeaderError, match=r"^wave3\.csv: expected header"):
        parse_survey_csv(",".join(columns), "wave3.csv")


def test_empty_file_is_an_error() -> None:
    with pytest.raises(CsvHeaderError, match="found an empty file"):
        parse_survey_csv("", "empty.csv")


def test_row_with_missing_cell_names_its_line() -> None:
    text = f"{HEADER}\n3001,07/09/2026,3,2005,1,1,0,1,0,0\n3002,1\n"

    with pytest.raises(CsvRowLengthError) as caught:
        parse_survey_csv(text, "wave3.csv")

    assert str(caught.value) == (
        "wave3.csv, line 3: expected 10 cells, found 2"
    )


@pytest.mark.parametrize(
    "error",
    [
        CsvHeaderError("a.csv", ("x", "y"), ("y",)),
        CsvRowLengthError("a.csv", 3, (10, 2)),
    ],
)
def test_csv_errors_survive_pickling(error: Exception) -> None:
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - own data

    assert str(restored) == str(error)


def test_batch_json_holds_rows_under_respondents_key() -> None:
    body = json.loads(to_batch_json([{"respondent_id": 1, "wave": None}]))

    assert body == {"respondents": [{"respondent_id": 1, "wave": None}]}


@pytest.mark.parametrize(
    ("file_name", "row_count"),
    [("wave1.csv", 12), ("wave2.csv", 11), ("wave3.csv", 12)],
)
def test_sample_files_parse(
    data_directory: Path, file_name: str, row_count: int
) -> None:
    csv_path = data_directory / file_name

    rows = parse_survey_csv(csv_path.read_text(), file_name)

    assert len(rows) == row_count
