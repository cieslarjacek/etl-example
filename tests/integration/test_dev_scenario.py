"""The sample waves through a dev container of the service image."""

from collections.abc import Iterator
from typing import Any

import httpx2
import pytest

from tests.integration.conftest import (
    Containers,
    http_client,
    respondents_in_wave,
    upload_file,
)

pytestmark = pytest.mark.integration

WAVE_FILES = ("wave1.csv", "wave2.csv", "wave3.csv")


@pytest.fixture(scope="module")
def dev_client(containers: Containers) -> Iterator[httpx2.Client]:
    service = containers.start("dev", containers.create_volume())
    with http_client(service) as client:
        yield client


@pytest.fixture(scope="module")
def wave_reports(dev_client: httpx2.Client) -> dict[str, dict[str, Any]]:
    """Batch reports of the three sample files, uploaded in order."""
    return {
        file_name: upload_file(dev_client, file_name)
        for file_name in WAVE_FILES
    }


@pytest.mark.parametrize("file_name", ["wave1.csv", "wave2.csv"])
def test_clean_wave_loads_every_row(
    wave_reports: dict[str, dict[str, Any]], file_name: str
) -> None:
    report = wave_reports[file_name]

    assert report["rows_received"] == report["rows_loaded"] == 12


def test_wave3_loads_nine_of_twelve_rows(
    wave_reports: dict[str, dict[str, Any]],
) -> None:
    report = wave_reports["wave3.csv"]

    assert (report["rows_received"], report["rows_loaded"]) == (12, 9)


def test_wave3_rejects_problem_rows(
    wave_reports: dict[str, dict[str, Any]],
) -> None:
    invalid_rows = wave_reports["wave3.csv"]["invalid_rows"]

    assert {(row["respondent_id"], row["reason"]) for row in invalid_rows} == {
        (3003, "underage"),
        (1005, "duplicated_id"),
        (3006, "invalid_value"),
    }


def test_wave3_corrects_usage_without_awareness(
    wave_reports: dict[str, dict[str, Any]],
) -> None:
    corrected_values = wave_reports["wave3.csv"]["corrected_values"]

    assert [
        (value["respondent_id"], value["column"]) for value in corrected_values
    ] == [(3007, "brand3_usage")]


def test_wave3_refreshes_waves_two_and_three(
    wave_reports: dict[str, dict[str, Any]],
) -> None:
    assert wave_reports["wave3.csv"]["refreshed_waves"] == [2, 3]


@pytest.mark.usefixtures("wave_reports")
def test_late_row_adds_a_respondent_to_wave_two(
    dev_client: httpx2.Client,
) -> None:
    response = dev_client.get("/summary")

    assert respondents_in_wave(response.json(), 2) == 13


@pytest.mark.usefixtures("wave_reports")
def test_missing_wave_is_not_found(dev_client: httpx2.Client) -> None:
    response = dev_client.get("/summary", params={"wave": 9})

    assert response.status_code == httpx2.codes.NOT_FOUND


def test_two_wave_selections_are_rejected(dev_client: httpx2.Client) -> None:
    response = dev_client.get("/summary", params={"wave": 1, "wave_last": 2})

    assert response.status_code == httpx2.codes.UNPROCESSABLE_CONTENT


def test_dev_serves_api_docs(dev_client: httpx2.Client) -> None:
    assert dev_client.get("/docs").status_code == httpx2.codes.OK
