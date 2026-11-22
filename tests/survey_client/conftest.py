"""A loopback HTTP server standing in for the service."""

import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import override

import pytest

# Loopback only: the server never leaves this machine.
LOOPBACK_HOST = "127.0.0.1"


@dataclass(frozen=True, slots=True)
class ReceivedRequest:
    """A request the loopback server received."""

    path: str
    content_type: str | None
    body: bytes


@dataclass(frozen=True, slots=True)
class LoopbackServer:
    """Base URL of a running loopback server and its requests."""

    url: str
    received_requests: list[ReceivedRequest] = field(default_factory=list)


type ServerFactory = Callable[[int, bytes], LoopbackServer]


def _handler_class(
    status: int, reply_body: bytes, server: LoopbackServer
) -> type[BaseHTTPRequestHandler]:
    """A request handler answering every POST with a fixed reply."""

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body_length = int(self.headers["Content-Length"])
            server.received_requests.append(
                ReceivedRequest(
                    self.path,
                    self.headers["Content-Type"],
                    self.rfile.read(body_length),
                )
            )
            self.send_response(status)
            self.send_header("Content-Length", str(len(reply_body)))
            self.end_headers()
            self.wfile.write(reply_body)

        @override
        def log_message(self, format: str, *args: object) -> None:
            """Keep test output free of access logs."""

    return _Handler


@pytest.fixture
def start_server() -> Iterator[ServerFactory]:
    """Start loopback servers replying with a given status and body."""
    running: list[tuple[HTTPServer, threading.Thread]] = []

    def start(status: int, reply_body: bytes) -> LoopbackServer:
        http_server = HTTPServer((LOOPBACK_HOST, 0), BaseHTTPRequestHandler)
        server = LoopbackServer(
            f"http://{LOOPBACK_HOST}:{http_server.server_port}"
        )
        http_server.RequestHandlerClass = _handler_class(
            status, reply_body, server
        )
        thread = threading.Thread(target=http_server.serve_forever)
        thread.start()
        running.append((http_server, thread))
        return server

    yield start

    for http_server, thread in running:
        http_server.shutdown()
        http_server.server_close()
        thread.join()
