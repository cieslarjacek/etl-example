import pickle

import pytest

from survey_etl.storage import (
    InvalidSelectionError,
    RespondentConflictError,
    SummaryNotFoundError,
)


@pytest.mark.parametrize(
    "error",
    [
        RespondentConflictError("UNIQUE failed"),
        SummaryNotFoundError(),
        InvalidSelectionError("wave range starts at 3, after its end 2"),
    ],
)
def test_database_errors_survive_pickling(error: Exception) -> None:
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - own data

    assert str(restored) == str(error)
