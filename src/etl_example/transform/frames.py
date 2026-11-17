"""Conversion between validated rows, pandas frames and records.

The frame index holds each row's 1-based position in the batch, so
corrections point back to the uploaded row.
"""

from collections.abc import Sequence
from typing import Final

import pandas as pd

from etl_example.survey import LAYOUT, SurveyLayout
from etl_example.validate import ValidRow

__all__ = [
    "NULLABLE_INTEGER",
    "build_frame",
    "frame_to_records",
]

# Keeps unanswered questions as integer type <NA>.
# Plain int would turn them to float type NaN.
NULLABLE_INTEGER: Final = pd.Int64Dtype()


def build_frame(
    rows: Sequence[ValidRow],
    layout: SurveyLayout = LAYOUT,
    integer_dtype: pd.Int64Dtype = NULLABLE_INTEGER,
) -> pd.DataFrame:
    """Build a frame of valid rows, indexed by row number.

    Args:
        rows: Rows that passed validation.
        layout: Survey layout declaring the columns.
        integer_dtype: Dtype of the integer columns.

    Returns:
        One frame row per valid row, with nullable integer columns.
    """
    frame = pd.DataFrame.from_records(
        [dict(row.values) for row in rows],
        index=[row.row_number for row in rows],
        columns=list(layout.input_columns),
    )
    integer_columns = [
        column
        for column in layout.input_columns
        if column != layout.columns.interview_date
    ]

    return frame.astype(dict.fromkeys(integer_columns, integer_dtype))


def frame_to_records(frame: pd.DataFrame) -> tuple[dict[str, object], ...]:
    """Convert a frame to records of plain Python values.

    Database drivers cannot bind pandas' missing-value marker or numpy
    numbers, so values become Python objects and ``<NA>`` becomes None.

    Args:
        frame: Rows to convert.

    Returns:
        One dictionary per row, keyed by column name.
    """
    plain_frame = frame.astype(object).where(frame.notna(), None)

    return tuple(
        {str(column): value for column, value in record.items()}
        for record in plain_frame.to_dict(orient="records")
    )
