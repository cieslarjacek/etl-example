"""The sample CSV files in data/ through the client and the API.

Waves 1 and 2 load cleanly; wave 3 carries one row of each problem the
pipeline reports and one late wave 2 row.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from survey_client import build_batch_body, parse_survey_csv
from survey_etl.settings import Environment
from tests.unit.survey_etl.api.conftest import client_for

DATA_DIRECTORY = Path(__file__).parents[3] / "data"


def upload_file(client: TestClient, file_name: str) -> dict[str, Any]:
    """Convert a sample file as the client does and post it."""
    csv_path = DATA_DIRECTORY / file_name
    survey_rows = parse_survey_csv(
        csv_path.read_text(encoding="utf-8-sig"), file_name
    )
    response = client.post("/batches", json=build_batch_body(survey_rows))
    assert response.status_code == 200, response.text
    report: dict[str, Any] = response.json()

    return report


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with client_for(Environment.DEV, database_url) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("file_name", "wave"), [("wave1.csv", 1), ("wave2.csv", 2)]
)
def test_clean_wave_file_loads_every_row(
    client: TestClient, file_name: str, wave: int
) -> None:
    report = upload_file(client, file_name)

    assert report["rows_received"] == report["rows_loaded"] == 12
    assert report["invalid_rows"] == report["corrected_values"] == []
    assert report["refreshed_waves"] == [wave]


def test_wave3_file_reports_its_problem_rows(client: TestClient) -> None:
    upload_file(client, "wave1.csv")
    upload_file(client, "wave2.csv")

    report = upload_file(client, "wave3.csv")

    assert (report["rows_received"], report["rows_loaded"]) == (12, 9)
    assert {
        (row["respondent_id"], row["reason"]) for row in report["invalid_rows"]
    } == {(3003, "underage"), (1005, "duplicated_id"), (3006, "invalid_value")}
    assert [
        (value["respondent_id"], value["column"])
        for value in report["corrected_values"]
    ] == [(3007, "brand3_usage")]


def test_wave3_file_refreshes_wave_of_late_row(client: TestClient) -> None:
    upload_file(client, "wave1.csv")
    upload_file(client, "wave2.csv")

    report = upload_file(client, "wave3.csv")

    assert report["refreshed_waves"] == [2, 3]
