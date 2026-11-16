"""Runtime settings for the dev/test and prod environments."""

import enum
import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel

__all__ = [
    "DEFAULT_SETTINGS",
    "DefaultVariable",
    "Environment",
    "Settings",
    "UnknownEnvironmentError",
    "settings_from_environ",
]


class DefaultVariable(BaseModel):
    """Placeholder."""

    environment: str = "APP_ENV"
    database_url: str = "DATABASE_URL"


DEFAULT_VARIABLES = DefaultVariable()


class Environment(enum.StrEnum):
    """Deployment environment the application runs in."""

    DEV = "dev"
    PROD = "prod"


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration of one running application instance.

    Attributes:
        environment: Environment the instance runs in.
        database_url: SQLAlchemy database URL.
        log_level: Standard logging level name, e.g. ``"INFO"``.
        is_docs_enabled: Whether the OpenAPI docs pages are served.
    """

    environment: Environment
    database_url: str
    log_level: str
    is_docs_enabled: bool

    def __post_init__(self) -> None:
        """Validate the database URL and the log level name.

        Raises:
            ValueError: If the URL is empty or the level is unknown.
        """
        if not self.database_url:
            raise ValueError("'database_url' must not be empty")
        if self.log_level not in logging.getLevelNamesMapping():
            raise ValueError(f"unknown 'log_level': {self.log_level!r}")


# SQLite paths are relative to the working directory - "/app" in Docker.
DEFAULT_SETTINGS: Final = MappingProxyType(
    {
        Environment.DEV: Settings(
            environment=Environment.DEV,
            database_url="sqlite:///var/dev.db",
            log_level="DEBUG",
            is_docs_enabled=True,
        ),
        Environment.PROD: Settings(
            environment=Environment.PROD,
            database_url="sqlite:///var/prod.db",
            log_level="INFO",
            is_docs_enabled=False,
        ),
    }
)


class UnknownEnvironmentError(ValueError):
    """The environment variable is missing or names no environment."""

    def __init__(self, variable: str, value: str | None) -> None:
        """Store the variable name and the value found.

        Args:
            variable: Name of the environment variable read.
            value: Value found, or None when the variable is unset.
        """
        super().__init__(variable, value)
        self.variable = variable
        self.value = value

    def __str__(self) -> str:
        """Name the variable, the allowed values and the value found."""
        allowed = ", ".join(Environment)
        return (
            f"{self.variable} must be one of: {allowed}; found {self.value!r}"
        )


def settings_from_environ(
    environ: Mapping[str, str],
    defaults: Mapping[Environment, Settings] = DEFAULT_SETTINGS,
    variables: DefaultVariable = DEFAULT_VARIABLES,
) -> Settings:
    """Select the settings named by the environment variables.

    Args:
        environ: Environment variables, usually ``os.environ``.
        variables: Variables naming the environment and
            overriding the database URL.
        defaults: Settings for each environment.

    Returns:
        The environment's default settings, with the database URL
        replaced when the override variable is set.

    Raises:
        UnknownEnvironmentError: If the environment variable is unset
            or names no known environment.
    """
    environment_name = environ.get(variables.environment)
    if environment_name is None or environment_name not in Environment:
        raise UnknownEnvironmentError(variables.environment, environment_name)
    environment = Environment(environment_name)
    settings = defaults[environment]

    database_url = environ.get(variables.database_url)
    if database_url is None:
        return settings

    return replace(settings, database_url=database_url)
