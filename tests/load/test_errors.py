import pickle

import pytest

from etl_example.load import (
    RespondentConflictError,
    WaveNotFoundError,
)


@pytest.mark.parametrize(
    "error",
    [WaveNotFoundError(7), RespondentConflictError("UNIQUE failed")],
)
def test_database_errors_survive_pickling(error: Exception) -> None:
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - own data

    assert str(restored) == str(error)
