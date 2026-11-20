import pickle

import pytest

from survey_etl.settings import (
    Environment,
    EnvironmentVariables,
    Settings,
    UnknownEnvironmentError,
    settings_from_environ,
)


def test_dev_environment_enables_docs_and_debug_logging() -> None:
    settings = settings_from_environ({"APP_ENV": "dev"})

    assert settings.environment is Environment.DEV
    assert settings.is_docs_enabled
    assert settings.log_level == "DEBUG"
    assert settings.database_url == "sqlite:///var/dev.db"


def test_prod_environment_disables_docs() -> None:
    settings = settings_from_environ({"APP_ENV": "prod"})

    assert settings.environment is Environment.PROD
    assert not settings.is_docs_enabled
    assert settings.log_level == "INFO"
    assert settings.database_url == "sqlite:///var/prod.db"


def test_database_url_variable_overrides_default() -> None:
    environ = {"APP_ENV": "prod", "DATABASE_URL": "sqlite:///other.db"}

    settings = settings_from_environ(environ)

    assert settings.database_url == "sqlite:///other.db"


def test_missing_environment_variable_is_an_error() -> None:
    with pytest.raises(UnknownEnvironmentError, match="found None"):
        settings_from_environ({})


def test_unknown_environment_error_lists_allowed_values() -> None:
    with pytest.raises(UnknownEnvironmentError) as caught:
        settings_from_environ({"APP_ENV": "staging"})

    assert str(caught.value) == (
        "APP_ENV must be one of: dev, prod; found 'staging'"
    )


def test_unknown_environment_error_survives_pickling() -> None:
    error = UnknownEnvironmentError("APP_ENV", "staging")

    restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - own data

    assert str(restored) == str(error)


def test_empty_database_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="database_url"):
        Settings(Environment.DEV, "", "DEBUG", is_docs_enabled=True)


def test_unknown_log_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="log_level"):
        Settings(Environment.DEV, "sqlite://", "LOUD", is_docs_enabled=True)


def test_custom_variable_names_are_read() -> None:
    variables = EnvironmentVariables("STAGE", "DB_URL")
    environ = {"STAGE": "prod", "DB_URL": "sqlite:///other.db"}

    settings = settings_from_environ(environ, variables=variables)

    assert settings.environment is Environment.PROD
    assert settings.database_url == "sqlite:///other.db"


def test_empty_variable_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        EnvironmentVariables(environment="")


def test_equal_variable_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="must differ"):
        EnvironmentVariables("APP_ENV", "APP_ENV")


def test_default_variable_names_cannot_be_changed() -> None:
    variables = EnvironmentVariables()

    with pytest.raises(AttributeError):
        variables.environment = "OTHER"  # type: ignore[misc]
