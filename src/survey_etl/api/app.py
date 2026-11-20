"""The API application: settings, database, routes and error replies."""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from importlib import metadata
from typing import Final

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, create_engine

from survey_etl.api.routes import build_router
from survey_etl.settings import Settings
from survey_etl.storage import (
    InvalidSelectionError,
    RespondentConflictError,
    SummaryNotFoundError,
    SurveyDatabase,
    define_tables,
)

__all__ = [
    "SERVICE_INFO",
    "ServiceInfo",
    "create_app",
]


@dataclass(frozen=True, slots=True)
class ServiceInfo:
    """Static facts about the service.

    Attributes:
        title: Title shown in the OpenAPI docs.
        distribution: Installed package name, used to read the version.
        logger_name: Root logger of the package.
        docs_path: Path of the Swagger UI when docs are enabled.
        openapi_path: Path of the OpenAPI schema when docs are enabled.
    """

    title: str = "survey_etl"
    distribution: str = "etl-example"
    logger_name: str = "survey_etl"
    docs_path: str = "/docs"
    openapi_path: str = "/openapi.json"


SERVICE_INFO: Final = ServiceInfo()


def _db_engine_lifespan(
    engine: Engine,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Return a lifespan closing the engine's connections on exit."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        engine.dispose()

    return lifespan


def _summary_not_found(_: Request, error: Exception) -> JSONResponse:
    """Answer 404 when no stored summary matches the selection."""
    return JSONResponse({"detail": str(error)}, status.HTTP_404_NOT_FOUND)


def _invalid_selection(_: Request, error: Exception) -> JSONResponse:
    """Answer 422 for a contradictory or impossible selection."""
    return JSONResponse(
        {"detail": str(error)}, status.HTTP_422_UNPROCESSABLE_CONTENT
    )


def _respondent_conflict(_: Request, error: Exception) -> JSONResponse:
    """Answer 409 when a concurrent batch stored the same IDs."""
    return JSONResponse({"detail": str(error)}, status.HTTP_409_CONFLICT)


def create_app(
    settings: Settings, service: ServiceInfo = SERVICE_INFO
) -> FastAPI:
    """Create the API application for the given settings.

    Args:
        settings: Settings of the running environment.
        service: Static facts about the service.

    Returns:
        The application with the database schema created.
    """
    logging.getLogger(service.logger_name).setLevel(settings.log_level)
    db_engine = create_engine(settings.database_url)
    database = SurveyDatabase(db_engine, define_tables())
    database.create_schema()

    is_docs_enabled = settings.is_docs_enabled
    app = FastAPI(
        title=service.title,
        version=metadata.version(service.distribution),
        docs_url=service.docs_path if is_docs_enabled else None,
        openapi_url=service.openapi_path if is_docs_enabled else None,
        redoc_url=None,
        lifespan=_db_engine_lifespan(db_engine),
    )
    app.state.settings = settings
    app.state.database = database
    app.include_router(build_router())
    app.add_exception_handler(SummaryNotFoundError, _summary_not_found)
    app.add_exception_handler(InvalidSelectionError, _invalid_selection)
    app.add_exception_handler(RespondentConflictError, _respondent_conflict)

    return app
