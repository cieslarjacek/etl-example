import socket
from urllib.error import URLError

import pytest

from survey_client import (
    HttpReply,
    UnsupportedUrlError,
    batches_url,
    post_json,
)
from tests.survey_client.conftest import LOOPBACK_HOST, ServerFactory

# ---- HttpReply ----


@pytest.mark.parametrize("status", [99, 600])
def test_reply_rejects_status_outside_http_range(status: int) -> None:
    with pytest.raises(ValueError, match="status"):
        HttpReply(status, b"")


@pytest.mark.parametrize("status", [200, 201, 299])
def test_2xx_reply_is_success(status: int) -> None:
    assert HttpReply(status, b"").is_success


@pytest.mark.parametrize("status", [100, 302, 409, 422, 500])
def test_other_reply_is_not_success(status: int) -> None:
    assert not HttpReply(status, b"").is_success


# ---- batches_url ----


@pytest.mark.parametrize(
    ("api_url", "expected_url"),
    [
        ("http://localhost:8000", "http://localhost:8000/batches"),
        ("http://localhost:8000/", "http://localhost:8000/batches"),
        ("https://example.org/survey", "https://example.org/survey/batches"),
    ],
)
def test_batches_url_appends_endpoint_path(
    api_url: str, expected_url: str
) -> None:
    assert batches_url(api_url) == expected_url


@pytest.mark.parametrize(
    "api_url", ["ftp://localhost", "file:///etc/passwd", "localhost:8000"]
)
def test_batches_url_rejects_non_http_url(api_url: str) -> None:
    with pytest.raises(UnsupportedUrlError, match="http, https"):
        batches_url(api_url)


# ---- post_json ----


def test_post_sends_json_body(start_server: ServerFactory) -> None:
    server = start_server(200, b"{}")

    post_json(f"{server.url}/batches", b'{"respondents": []}')

    (request,) = server.received_requests
    assert request.path == "/batches"
    assert request.content_type == "application/json"
    assert request.body == b'{"respondents": []}'


def test_post_returns_success_reply(start_server: ServerFactory) -> None:
    server = start_server(200, b'{"rows_loaded": 0}')

    reply = post_json(server.url, b"{}")

    assert reply == HttpReply(200, b'{"rows_loaded": 0}')


def test_post_returns_error_reply_without_raising(
    start_server: ServerFactory,
) -> None:
    server = start_server(422, b'{"detail": "invalid"}')

    reply = post_json(server.url, b"{}")

    assert reply == HttpReply(422, b'{"detail": "invalid"}')


def test_post_to_closed_port_raises_url_error() -> None:
    with socket.socket() as probe:
        probe.bind((LOOPBACK_HOST, 0))
        closed_port = probe.getsockname()[1]

    with pytest.raises(URLError):
        post_json(f"http://{LOOPBACK_HOST}:{closed_port}", b"{}")
