import pytest

from survey_client import (
    InvalidHeaderError,
    MissingHeaderError,
    RowLengthError,
    SurveyRow,
    build_batch_body,
    parse_cell,
    parse_survey_csv,
)

SOURCE = "wave.csv"


# ---- parse_cell ----


@pytest.mark.parametrize("cell_text", ["", "   "])
def test_empty_cell_is_none(cell_text: str) -> None:
    assert parse_cell(cell_text) is None


@pytest.mark.parametrize(
    ("cell_text", "expected_number"),
    [("7", 7), ("-3", -3), ("+2", 2), (" 1 ", 1), ("007", 7)],
)
def test_whole_number_cell_is_int(
    cell_text: str, expected_number: int
) -> None:
    assert parse_cell(cell_text) == expected_number


@pytest.mark.parametrize(
    "cell_text",
    ["15/09/2026", "1.5", "yes", "1_000", "\N{FULLWIDTH DIGIT ONE}", " 2a "],
)
def test_other_cell_is_text_unchanged(cell_text: str) -> None:
    assert parse_cell(cell_text) == cell_text


# ---- parse_survey_csv ----


def test_rows_are_keyed_by_header_with_parsed_cells() -> None:
    csv_text = "respondent_id,interview_date,brand1_usage\n1001,02/03/2026,\n"

    survey_rows = parse_survey_csv(csv_text, SOURCE)

    assert survey_rows == (
        {
            "respondent_id": 1001,
            "interview_date": "02/03/2026",
            "brand1_usage": None,
        },
    )


def test_rows_keep_file_order() -> None:
    csv_text = "respondent_id\n2\n1\n3\n"

    survey_rows = parse_survey_csv(csv_text, SOURCE)

    assert [row["respondent_id"] for row in survey_rows] == [2, 1, 3]


def test_blank_lines_are_skipped() -> None:
    csv_text = "\n\nrespondent_id,wave\n\n1001,1\n\n1002,1\n"

    survey_rows = parse_survey_csv(csv_text, SOURCE)

    assert survey_rows == (
        {"respondent_id": 1001, "wave": 1},
        {"respondent_id": 1002, "wave": 1},
    )


def test_windows_line_endings_are_read() -> None:
    csv_text = "respondent_id,wave\r\n1001,1\r\n"

    survey_rows = parse_survey_csv(csv_text, SOURCE)

    assert survey_rows == ({"respondent_id": 1001, "wave": 1},)


def test_quoted_cell_may_contain_a_comma() -> None:
    csv_text = 'respondent_id,note\n1001,"late, by phone"\n'

    survey_rows = parse_survey_csv(csv_text, SOURCE)

    assert survey_rows[0]["note"] == "late, by phone"


def test_header_without_rows_gives_no_rows() -> None:
    assert parse_survey_csv("respondent_id,wave\n", SOURCE) == ()


@pytest.mark.parametrize("csv_text", ["", "\n\n"])
def test_text_without_header_is_rejected(csv_text: str) -> None:
    with pytest.raises(MissingHeaderError, match=SOURCE):
        parse_survey_csv(csv_text, SOURCE)


@pytest.mark.parametrize(
    "header", ["respondent_id,wave,wave", "respondent_id,,wave", "id, "]
)
def test_header_with_repeated_or_empty_name_is_rejected(header: str) -> None:
    with pytest.raises(InvalidHeaderError, match=SOURCE):
        parse_survey_csv(f"{header}\n", SOURCE)


@pytest.mark.parametrize("data_line", ["1001", "1001,1,extra"])
def test_row_with_wrong_field_count_is_rejected(data_line: str) -> None:
    csv_text = f"respondent_id,wave\n1001,1\n{data_line}\n"

    with pytest.raises(RowLengthError) as raised:
        parse_survey_csv(csv_text, SOURCE)

    assert raised.value.location.line_number == 3


# ---- build_batch_body ----


def test_batch_body_lists_rows_under_respondents() -> None:
    survey_rows: tuple[SurveyRow, ...] = (
        {"respondent_id": 1001},
        {"respondent_id": 1002},
    )

    body = build_batch_body(survey_rows)

    assert body == {
        "respondents": [{"respondent_id": 1001}, {"respondent_id": 1002}]
    }


def test_batch_body_of_no_rows_is_empty_list() -> None:
    assert build_batch_body(()) == {"respondents": []}
