"""Helpers building transform inputs from raw rows."""

from collections.abc import Mapping, Sequence

import pandas as pd

from etl_example.transform import build_frame
from etl_example.validate import RowValidator, ValidRow


def valid_rows(raw_rows: Sequence[Mapping[str, object]]) -> list[ValidRow]:
    """Validate raw rows, failing the test if any is rejected."""
    result = RowValidator().validate(raw_rows)
    assert result.invalid_rows == ()

    return list(result.valid_rows)


def frame_of(raw_rows: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    """Build the frame of raw rows that are all valid."""
    return build_frame(valid_rows(raw_rows))
