from importlib import metadata

import etl_example


def test_package_is_installed_with_its_metadata() -> None:
    distribution = metadata.distribution("etl-example")

    assert distribution.version == "0.1.0"
    assert distribution.metadata["Requires-Python"] == ">=3.14"


def test_package_is_importable() -> None:
    assert etl_example.__name__ == "etl_example"
