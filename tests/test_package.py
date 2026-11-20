from importlib import metadata

import survey_etl


def test_package_is_installed_with_its_metadata() -> None:
    distribution = metadata.distribution("etl-example")

    assert distribution.version == "0.1.0"
    assert distribution.metadata["Requires-Python"] == ">=3.14"


def test_package_is_importable() -> None:
    assert survey_etl.__name__ == "survey_etl"
