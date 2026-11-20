"""Test clients of the API, one per environment."""

import dataclasses
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from etl_example.api import create_app
from etl_example.settings import DEFAULT_SETTINGS, Environment


def client_for(environment: Environment, database_url: str) -> TestClient:
    """A test client of the app for an environment and database."""
    settings = dataclasses.replace(
        DEFAULT_SETTINGS[environment], database_url=database_url
    )

    return TestClient(create_app(settings))


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    """A test client of the dev app, run through its lifespan."""
    with client_for(Environment.DEV, database_url) as test_client:
        yield test_client


@pytest.fixture
def prod_client(database_url: str) -> Iterator[TestClient]:
    """A test client of the prod app, run through its lifespan."""
    with client_for(Environment.PROD, database_url) as test_client:
        yield test_client
