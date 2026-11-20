from collections.abc import Mapping, Sequence
from importlib import metadata

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from survey_etl.storage import (
    RespondentConflictError,
    SurveyDatabase,
    define_tables,
)


def test_dev_serves_docs(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_prod_hides_docs(prod_client: TestClient) -> None:
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404


def test_api_version_is_the_package_version(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert schema["info"]["version"] == metadata.version("etl-example")


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
    assert "already stored" in response.json()["detail"]


@pytest.mark.parametrize(
    ("state_name", "path"),
    [("database", "/summary"), ("settings", "/health")],
)
def test_misconfigured_app_state_is_a_type_error(
    client: TestClient, state_name: str, path: str
) -> None:
    setattr(client.app.state, state_name, "misconfigured")  # type: ignore[attr-defined]

    with pytest.raises(TypeError, match=f"app.state.{state_name}"):
        client.get(path)
