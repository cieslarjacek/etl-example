"""Sending a batch body to the service over HTTP."""

import urllib.request
from collections.abc import Callable, Collection
from dataclasses import dataclass
from http import HTTPStatus
from typing import ClassVar, Final
from urllib.error import HTTPError
from urllib.parse import urlsplit

from survey_client.errors import UnsupportedUrlError

__all__ = [
    "BATCHES_PATH",
    "HTTP_SCHEMES",
    "JSON_CONTENT_TYPE",
    "TIMEOUT_SECONDS",
    "HttpReply",
    "Poster",
    "batches_url",
    "post_json",
]

BATCHES_PATH: Final = "/batches"
HTTP_SCHEMES: Final = frozenset({"http", "https"})
JSON_CONTENT_TYPE: Final = "application/json"
# Loading and summarising a batch takes well under a second; the
# margin covers a container that is still starting.
TIMEOUT_SECONDS: Final = 30.0


@dataclass(frozen=True, slots=True)
class HttpReply:
    """Status and body of the service's reply.

    Attributes:
        status: HTTP status code.
        body: Raw reply body.
        status_range: Codes HTTP allows (RFC 9110, section 15).
    """

    status: int
    body: bytes
    status_range: ClassVar[range] = range(100, 600)

    def __post_init__(self) -> None:
        """Reject codes outside the HTTP status range.

        Raises:
            ValueError: If ``status`` is outside ``status_range``.
        """
        if self.status not in self.status_range:
            message = (
                f"status must be in {self.status_range}, got {self.status}"
            )
            raise ValueError(message)

    @property
    def is_success(self) -> bool:
        """Whether the status is a 2xx success."""
        return HTTPStatus.OK <= self.status < HTTPStatus.MULTIPLE_CHOICES


# Sends a JSON body to a URL and returns the reply.
type Poster = Callable[[str, bytes], HttpReply]


def batches_url(
    api_url: str,
    path: str = BATCHES_PATH,
    allowed_schemes: Collection[str] = HTTP_SCHEMES,
) -> str:
    """Build the batch upload URL from the service's base URL.

    Args:
        api_url: Base URL of the service, such as
            ``http://localhost:8000``.
        path: Path of the batch upload endpoint.
        allowed_schemes: URL schemes the client accepts.

    Returns:
        The URL of the batch upload endpoint.

    Raises:
        UnsupportedUrlError: If the URL's scheme is not allowed.
    """
    if urlsplit(api_url).scheme not in allowed_schemes:
        raise UnsupportedUrlError(api_url, allowed_schemes)

    return api_url.rstrip("/") + path


def post_json(
    url: str,
    body: bytes,
    timeout_seconds: float = TIMEOUT_SECONDS,
    content_type: str = JSON_CONTENT_TYPE,
) -> HttpReply:
    """Send a JSON body with POST and return the reply.

    Error statuses are returned, not raised: the service explains a
    rejected batch in the reply body.

    Args:
        url: URL to post to; ``batches_url`` checks its scheme.
        body: JSON body, encoded.
        timeout_seconds: Time to wait for the connection and reply.
        content_type: Content type of the body.

    Returns:
        The reply's status and body.

    Raises:
        urllib.error.URLError: If the service cannot be reached.
    """
    request = urllib.request.Request(  # noqa: S310 - scheme checked
        url, data=body, headers={"Content-Type": content_type}, method="POST"
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - scheme checked
            request, timeout=timeout_seconds
        ) as response:
            return HttpReply(response.status, response.read())
    except HTTPError as error:
        with error:
            return HttpReply(error.code, error.read())
