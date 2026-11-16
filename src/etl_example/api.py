"""HTTP API: upload survey batches and read wave summaries."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from importlib import metadata
from typing import Annotated, Final

from fastapi import APIRouter, Depends, FastAPI, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy import Engine, create_engine

from etl_example.database import (
    RespondentConflictError,
    SurveyDatabase,
    WaveNotFoundError,
    define_tables,
)
from etl_example.pipeline import process_batch
from etl_example.reports import BatchReport, WaveSummary
from etl_example.settings import Environment, Settings

__all__ = [
    "SERVICE_INFO",
    "BatchRequest",
    "HealthResponse",
    "ServiceInfo",
    "create_app",
]

router = APIRouter()


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

    title: str = "etl-example"
    distribution: str = "etl-example"
    logger_name: str = "etl_example"
    docs_path: str = "/docs"
    openapi_path: str = "/openapi.json"


SERVICE_INFO: Final = ServiceInfo()


class BatchRequest(BaseModel):
    """Request body of a batch upload.

    Rows are only checked to be JSON objects here; their values are
    validated row by row in the pipeline, so one bad row does not
    reject the whole batch.

    Attributes:
        respondents: Survey rows, one object per respondent.
    """

    model_config = ConfigDict(extra="forbid")

    respondents: list[dict[str, JsonValue]]


@dataclass(frozen=True, slots=True)
class HealthResponse:
    """Response of the health check.

    Attributes:
        status: Always ``"ok"`` when the service responds.
        environment: Environment the service runs in.
    """

    status: str
    environment: Environment


def _database(request: Request) -> SurveyDatabase:
    """Return the database stored on the application at start-up."""
    database = request.app.state.database
    if not isinstance(database, SurveyDatabase):
        raise TypeError("app.state.database must hold a SurveyDatabase")
    return database


def _settings(request: Request) -> Settings:
    """Return the settings stored on the application at start-up."""
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise TypeError("app.state.settings must hold Settings")
    return settings


@router.get("/health")
def get_health(
    settings: Annotated[Settings, Depends(_settings)],
) -> HealthResponse:
    """Report that the service is up and its environment."""
    return HealthResponse(status="ok", environment=settings.environment)


@router.post("/batches")
def post_batch(
    batch: BatchRequest,
    database: Annotated[SurveyDatabase, Depends(_database)],
) -> BatchReport:
    """Validate, clean, transform and store a batch of survey rows.

    Waves receiving new rows get their summaries recalculated.
    """
    return process_batch(batch.respondents, database)


@router.get("/waves/{wave}/summary")
def get_wave_summary(
    wave: Annotated[int, Path(ge=1)],
    database: Annotated[SurveyDatabase, Depends(_database)],
) -> WaveSummary:
    """Return respondent, awareness and usage totals by age."""
    return database.read_wave_summary(wave)


def _wave_not_found(_: Request, error: Exception) -> JSONResponse:
    """Answer 404 for a wave without a stored summary."""
    return JSONResponse({"detail": str(error)}, status.HTTP_404_NOT_FOUND)


def _respondent_conflict(_: Request, error: Exception) -> JSONResponse:
    """Answer 409 when a concurrent batch stored the same IDs."""
    return JSONResponse({"detail": str(error)}, status.HTTP_409_CONFLICT)


def _engine_lifespan(
    engine: Engine,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Return a lifespan closing the engine's connections on exit."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    return lifespan


def create_app(
    settings: Settings, service: ServiceInfo = SERVICE_INFO
) -> FastAPI:
    """Create the API application for the given settings.

    Args:
        settings: Settings of the running environment.
        service: Static facts about the service.

    Returns:
        The application, with the database schema created.
    """
    logging.getLogger(service.logger_name).setLevel(settings.log_level)
    engine = create_engine(settings.database_url)
    database = SurveyDatabase(engine, define_tables())
    database.create_schema()
    is_docs_enabled = settings.is_docs_enabled
    app = FastAPI(
        title=service.title,
        version=metadata.version(service.distribution),
        docs_url=service.docs_path if is_docs_enabled else None,
        openapi_url=service.openapi_path if is_docs_enabled else None,
        redoc_url=None,
        lifespan=_engine_lifespan(engine),
    )
    app.state.settings = settings
    app.state.database = database
    app.include_router(router)
    app.add_exception_handler(WaveNotFoundError, _wave_not_found)
    app.add_exception_handler(RespondentConflictError, _respondent_conflict)
    return app
