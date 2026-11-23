"""A prod container of the service image."""

from collections.abc import Iterator

import httpx2
import pytest

from tests.integration.conftest import (
    Containers,
    http_client,
    respondents_in_wave,
    upload_file,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def prod_client(containers: Containers) -> Iterator[httpx2.Client]:
    service = containers.start("prod", containers.create_volume())
    with http_client(service) as client:
        yield client


def test_prod_reports_its_environment(prod_client: httpx2.Client) -> None:
    response = prod_client.get("/health")

    assert response.json() == {"status": "ok", "environment": "prod"}


def test_prod_hides_api_docs(prod_client: httpx2.Client) -> None:
    assert prod_client.get("/docs").status_code == httpx2.codes.NOT_FOUND


def test_data_survives_a_new_container_on_the_same_volume(
    containers: Containers,
) -> None:
    volume_name = containers.create_volume()
    first_service = containers.start("prod", volume_name)
    with http_client(first_service) as client:
        upload_file(client, "wave1.csv")
    containers.remove(first_service)

    second_service = containers.start("prod", volume_name)
    with http_client(second_service) as client:
        response = client.get("/summary", params={"wave": 1})

    assert respondents_in_wave(response.json(), 1) == 12
