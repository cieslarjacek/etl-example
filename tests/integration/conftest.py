"""Fixtures that run the service image in Docker.

The tests start their own containers, on ports Docker picks and with
their own volumes, so they never touch the containers of
``make docker-run``. INTEGRATION_IMAGE names the image to test (default
``etl-example:local``, built by ``make docker-build``). When
INTEGRATION_LOG_DIRECTORY is set, each container's log is saved there.
"""

import contextlib
import os
import subprocess
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx2
import pytest

from survey_client import build_batch_body, parse_survey_csv

IMAGE_VARIABLE = "INTEGRATION_IMAGE"
LOG_DIRECTORY_VARIABLE = "INTEGRATION_LOG_DIRECTORY"
DEFAULT_IMAGE = "etl-example:local"
CONTAINER_PORT = "8000/tcp"
NAME_PREFIX = "etl-example-it"
DATA_DIRECTORY = Path(__file__).parents[2] / "data"
# Start-up takes a few seconds; the margin covers a busy CI runner.
START_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 30.0


def run_docker(*arguments: str) -> str:
    """Run a docker command and return its standard output."""
    completed = subprocess.run(  # noqa: S603 - fixed docker arguments
        ["docker", *arguments],  # noqa: S607 - the docker CLI on PATH
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = (
            f"docker {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
        raise RuntimeError(message)
    return completed.stdout.strip()


def unique_name(*parts: str) -> str:
    """A container or volume name no other run uses."""
    return "-".join((NAME_PREFIX, *parts, uuid.uuid4().hex[:8]))


def wait_until_healthy(base_url: str, container_name: str) -> None:
    """Poll GET /health until it answers 200; fail with the logs."""
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        with contextlib.suppress(httpx2.TransportError):
            response = httpx2.get(f"{base_url}/health")
            if response.status_code == httpx2.codes.OK:
                return
        time.sleep(POLL_INTERVAL_SECONDS)
    container_log = run_docker("logs", container_name)
    message = (
        f"{container_name} gave no healthy answer at {base_url} within "
        f"{START_TIMEOUT_SECONDS} s; its log:\n{container_log}"
    )
    raise TimeoutError(message)


@dataclass(frozen=True, slots=True)
class Service:
    """A running service container."""

    container_name: str
    base_url: str


@dataclass
class Containers:
    """Starts service containers; removes them and their volumes."""

    image: str
    log_directory: Path | None
    container_names: list[str] = field(default_factory=list)
    volume_names: list[str] = field(default_factory=list)

    def create_volume(self) -> str:
        """Create an empty named volume and return its name."""
        volume_name = unique_name("volume")
        run_docker("volume", "create", volume_name)
        self.volume_names.append(volume_name)
        return volume_name

    def start(self, environment: str, volume_name: str) -> Service:
        """Start a container of the image; wait until it is healthy."""
        container_name = unique_name(environment)
        self.container_names.append(container_name)
        run_docker(
            "run",
            "--detach",
            "--name",
            container_name,
            "--env",
            f"APP_ENV={environment}",
            # No host port given: Docker picks a free one.
            "--publish",
            f"127.0.0.1::{CONTAINER_PORT}",
            "--volume",
            f"{volume_name}:/app/var",
            self.image,
        )
        host_address = run_docker("port", container_name, CONTAINER_PORT)
        service = Service(container_name, f"http://{host_address.split()[0]}")
        wait_until_healthy(service.base_url, container_name)
        return service

    def remove(self, service: Service) -> None:
        """Save the log of a container, then remove the container."""
        self._save_log(service.container_name)
        run_docker("rm", "--force", service.container_name)
        self.container_names.remove(service.container_name)

    def remove_all(self) -> None:
        """Remove every container and volume still left."""
        for container_name in self.container_names:
            self._save_log(container_name)
            run_docker("rm", "--force", container_name)
        for volume_name in self.volume_names:
            run_docker("volume", "rm", "--force", volume_name)

    def _save_log(self, container_name: str) -> None:
        if self.log_directory is None:
            return
        self.log_directory.mkdir(parents=True, exist_ok=True)
        log_path = self.log_directory / f"{container_name}.log"
        log_path.write_text(run_docker("logs", container_name), "utf-8")


@pytest.fixture(scope="session")
def containers() -> Iterator[Containers]:
    """The containers and volumes of the test session."""
    log_directory = os.environ.get(LOG_DIRECTORY_VARIABLE)
    started_containers = Containers(
        image=os.environ.get(IMAGE_VARIABLE, DEFAULT_IMAGE),
        log_directory=Path(log_directory) if log_directory else None,
    )
    yield started_containers
    started_containers.remove_all()


def http_client(service: Service) -> httpx2.Client:
    """An HTTP client for a running service."""
    return httpx2.Client(
        base_url=service.base_url, timeout=REQUEST_TIMEOUT_SECONDS
    )


def upload_file(client: httpx2.Client, file_name: str) -> dict[str, Any]:
    """Convert a sample file as survey_client does and post it."""
    csv_text = (DATA_DIRECTORY / file_name).read_text(encoding="utf-8-sig")
    body = build_batch_body(parse_survey_csv(csv_text, file_name))
    response = client.post("/batches", json=body)
    response.raise_for_status()
    report: dict[str, Any] = response.json()
    return report


def respondents_in_wave(summary: dict[str, Any], wave: int) -> int:
    """Total respondents of a wave in a GET /summary reply."""
    (wave_summary,) = [
        stored_wave
        for stored_wave in summary["waves"]
        if stored_wave["wave"] == wave
    ]
    return sum(
        category["respondents_total"]
        for category in wave_summary["age_categories"]
    )
