import dataclasses
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from etl_example.api import create_app
from etl_example.database import (
    RespondentConflictError,
    SurveyDatabase,
    define_tables,
)
from etl_example.settings import DEFAULT_SETTINGS, Environment
from etl_example.survey_csv import parse_survey_csv


def client_for(environment: Environment, database_url: str) -> TestClient:
    """A test client of the app for an environment and database."""
    settings = DEFAULT_SETTINGS[environment]
    app = create_app(dataclasses.replace(settings, database_url=database_url))
    return TestClient(app)


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    """A test client of the dev app, run through its lifespan."""
    with client_for(Environment.DEV, database_url) as test_client:
        yield test_client


def upload(
    client: TestClient, rows: Sequence[Mapping[str, object]]
) -> dict[str, Any]:
    """Post a batch and return the decoded response body."""
    response = client.post("/batches", json={"respondents": rows})
    assert response.status_code == 200, response.text
    report: dict[str, Any] = response.json()
    return report


def upload_file(client: TestClient, csv_path: Path) -> dict[str, Any]:
    """Post a sample wave file and return the decoded response body."""
    rows = parse_survey_csv(csv_path.read_text(), str(csv_path))
    return upload(client, rows)


def test_health_reports_environment(client: TestClient) -> None:
    response = client.get("/health")

    assert response.json() == {"status": "ok", "environment": "dev"}


def test_dev_serves_docs(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_prod_hides_docs(database_url: str) -> None:
    with client_for(Environment.PROD, database_url) as prod_client:
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 404


def test_upload_returns_batch_report(
    client: TestClient, raw_row: dict[str, object]
) -> None:
    report = upload(client, [raw_row, raw_row | {"wave": 0}])

    assert report["rows_received"] == 2
    assert report["rows_loaded"] == 1
    assert report["dropped_rows"][0]["reason"] == "invalid_value"
    assert report["refreshed_waves"] == [3]


def test_summary_lists_brand_totals_per_age_category(
    client: TestClient, raw_row: dict[str, object]
) -> None:
    upload(client, [raw_row])

    response = client.get("/waves/3/summary")

    assert response.json() == {
        "wave": 3,
        "age_categories": [
            {
                "age_category": "35-44",
                "respondents_total": 1,
                "brands": [
                    {
                        "brand": "brand1",
                        "awareness_total": 1,
                        "usage_total": 1,
                    },
                    {
                        "brand": "brand2",
                        "awareness_total": 1,
                        "usage_total": 0,
                    },
                    {
                        "brand": "brand3",
                        "awareness_total": 0,
                        "usage_total": 0,
                    },
                ],
            }
        ],
    }


def test_unknown_wave_is_not_found(client: TestClient) -> None:
    response = client.get("/waves/9/summary")

    assert response.status_code == 404
    assert response.json() == {"detail": "no summary stored for wave 9"}


def test_wave_below_one_is_unprocessable(client: TestClient) -> None:
    assert client.get("/waves/0/summary").status_code == 422


def test_body_without_respondents_is_unprocessable(client: TestClient) -> None:
    response = client.post("/batches", json={"rows": []})

    assert response.status_code == 422


def test_row_that_is_not_an_object_is_unprocessable(
    client: TestClient,
) -> None:
    response = client.post("/batches", json={"respondents": [1, 2]})

    assert response.status_code == 422


def test_concurrent_conflict_is_answered_with_409(
    client: TestClient, database_url: str, raw_row: dict[str, object]
) -> None:
    class ConflictingDatabase(SurveyDatabase):
        def load_new_respondents(
            self, records: Sequence[Mapping[str, object]]
        ) -> None:
            raise RespondentConflictError("UNIQUE constraint failed")

    engine = create_engine(database_url)
    conflicting_database = ConflictingDatabase(engine, define_tables())
    client.app.state.database = conflicting_database  # type: ignore[attr-defined]

    response = client.post("/batches", json={"respondents": [raw_row]})

    engine.dispose()
    assert response.status_code == 409


def test_wave_three_scenario_reports_and_refreshes_late_wave(
    client: TestClient, data_directory: Path
) -> None:
    upload_file(client, data_directory / "wave1.csv")
    upload_file(client, data_directory / "wave2.csv")

    report = upload_file(client, data_directory / "wave3.csv")

    assert report["rows_received"] == 12
    assert report["rows_loaded"] == 9
    assert [
        (issue["row_number"], issue["reason"])
        for issue in report["dropped_rows"]
    ] == [
        (7, "no_answers"),
        (9, "invalid_value"),
        (10, "duplicate_in_database"),
    ]
    assert [issue["row_number"] for issue in report["corrected_rows"]] == [3]
    assert report["refreshed_waves"] == [2, 3]


def test_late_row_completes_wave_two(
    client: TestClient, data_directory: Path
) -> None:
    for wave in (1, 2, 3):
        upload_file(client, data_directory / f"wave{wave}.csv")

    summary = client.get("/waves/2/summary").json()

    totals = [
        category["respondents_total"] for category in summary["age_categories"]
    ]
    assert sum(totals) == 12


@pytest.mark.parametrize(
    ("state_name", "path"),
    [("database", "/waves/1/summary"), ("settings", "/health")],
)
def test_misconfigured_app_state_is_a_type_error(
    client: TestClient, state_name: str, path: str
) -> None:
    setattr(client.app.state, state_name, "misconfigured")  # type: ignore[attr-defined]

    with pytest.raises(TypeError, match=f"app.state.{state_name}"):
        client.get(path)
