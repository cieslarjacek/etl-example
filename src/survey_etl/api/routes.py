"""HTTP routes: health check, batch upload and wave summaries."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from survey_etl.pipeline import BatchReport, process_batch
from survey_etl.settings import Environment, Settings
from survey_etl.storage import (
    AgeCategorySelection,
    SurveyDatabase,
    WaveSelection,
    WaveSummary,
)

__all__ = [
    "BatchRequest",
    "HealthResponse",
    "SummaryQuery",
    "SummaryResponse",
    "build_router",
]


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


class SummaryQuery(BaseModel):
    """Query string of ``GET /summary``.

    Give at most one way to select waves (``wave``, ``wave_last``, or
    ``wave_from``/``wave_to``) and one way to select age categories
    (``agecat``, or ``agecat_from``/``agecat_to``). Every parameter is
    optional - nothing given selects everything.

    Attributes:
        wave: A single wave.
        wave_last: The latest n stored waves.
        wave_from: First wave of a range.
        wave_to: Last wave of a range.
        agecat: A single age category, by position (1 = youngest).
        agecat_from: First age category of a range, by position.
        agecat_to: Last age category of a range, by position.
    """

    model_config = ConfigDict(extra="forbid")

    wave: int | None = Field(default=None, ge=1, description="A single wave.")
    wave_last: int | None = Field(
        default=None, ge=1, description="The latest n stored waves."
    )
    wave_from: int | None = Field(
        default=None, ge=1, description="First wave of a range."
    )
    wave_to: int | None = Field(
        default=None, ge=1, description="Last wave of a range."
    )
    agecat: int | None = Field(
        default=None,
        ge=1,
        description="A single age category by position, 1 = youngest.",
    )
    agecat_from: int | None = Field(
        default=None, ge=1, description="First age category of a range."
    )
    agecat_to: int | None = Field(
        default=None, ge=1, description="Last age category of a range."
    )

    def wave_selection(self) -> WaveSelection:
        """Return the selected waves.

        Returns:
            The wave selection described by the query.

        Raises:
            InvalidSelectionError: If the wave parameters contradict
                each other.
        """
        return WaveSelection(
            self.wave, self.wave_last, self.wave_from, self.wave_to
        )

    def age_category_selection(self) -> AgeCategorySelection:
        """Return the selected age categories.

        Returns:
            The age category selection described by the query.

        Raises:
            InvalidSelectionError: If the age category parameters
                contradict each other.
        """
        return AgeCategorySelection(
            self.agecat, self.agecat_from, self.agecat_to
        )


@dataclass(frozen=True, slots=True)
class SummaryResponse:
    """Response of ``GET /summary``.

    Attributes:
        waves: Summaries of the selected waves, oldest first.
    """

    waves: tuple[WaveSummary, ...]


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


def get_health(
    settings: Annotated[Settings, Depends(_settings)],
) -> HealthResponse:
    """Report that the service is up and its environment."""
    return HealthResponse(status="ok", environment=settings.environment)


def post_batch(
    batch: BatchRequest,
    database: Annotated[SurveyDatabase, Depends(_database)],
) -> BatchReport:
    """Validate, transform and load a batch of survey rows.

    Waves receiving new rows get their summaries recalculated.
    """
    return process_batch(batch.respondents, database)


def get_summary(
    query: Annotated[SummaryQuery, Query()],
    database: Annotated[SurveyDatabase, Depends(_database)],
) -> SummaryResponse:
    """Return respondent, awareness and usage totals by wave and age.

    Select waves with ``wave``, ``wave_last`` or ``wave_from`` and
    ``wave_to``; select age categories (1 = youngest) with ``agecat``
    or ``agecat_from`` and ``agecat_to``.
    """
    summaries = database.read_summaries(
        query.wave_selection(), query.age_category_selection()
    )

    return SummaryResponse(summaries)


def build_router() -> APIRouter:
    """Build the router with every endpoint of the API.

    Returns:
        A router to include in the application.
    """
    router = APIRouter()
    router.add_api_route("/health", get_health, methods=["GET"])
    router.add_api_route("/batches", post_batch, methods=["POST"])
    router.add_api_route("/summary", get_summary, methods=["GET"])

    return router
