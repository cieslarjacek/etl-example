"""ASGI entry point: builds the application from environment variables.

Run with ``uvicorn etl_example.api.asgi:create_application --factory``.
"""

import logging
import os
from typing import Final

from fastapi import FastAPI

from etl_example.api.app import create_app
from etl_example.settings import settings_from_environ

__all__ = ["LOG_FORMAT", "create_application"]

LOG_FORMAT: Final = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def create_application(log_format: str = LOG_FORMAT) -> FastAPI:
    """Create the application for the environment named by ``APP_ENV``.

    Also sends log records to standard error. ``create_app`` sets the
    package's level, other libraries keep the default WARNING.

    Args:
        log_format: Format of the log lines.

    Returns:
        The API application.

    Raises:
        UnknownEnvironmentError: If ``APP_ENV`` is unset or unknown.
    """
    logging.basicConfig(format=log_format)

    return create_app(settings_from_environ(os.environ))
