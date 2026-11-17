"""Running valid rows through every transformer, in order."""

from collections.abc import Sequence

from etl_example.survey import LAYOUT, SurveyLayout
from etl_example.transform.frames import build_frame
from etl_example.transform.reports import CorrectedValue
from etl_example.transform.transformers import (
    TRANSFORMERS,
    Transformer,
    TransformOutcome,
)
from etl_example.validate import ValidRow

__all__ = ["transform_rows"]


def transform_rows(
    rows: Sequence[ValidRow],
    transformers: Sequence[Transformer] = TRANSFORMERS,
    layout: SurveyLayout = LAYOUT,
) -> TransformOutcome:
    """Run valid rows through every transformer, in order.

    Args:
        rows: Rows that passed validation.
        transformers: Transformers to apply, in order.
        layout: Survey layout declaring the columns.

    Returns:
        Rows ready to be stored, with every correction in batch order.
    """
    frame = build_frame(rows, layout)
    corrections: list[CorrectedValue] = []

    for transformer in transformers:
        outcome = transformer(frame)
        frame = outcome.frame
        corrections += outcome.corrections

    ordered_corrections = sorted(
        corrections, key=lambda correction: correction.row_number
    )

    return TransformOutcome(frame, tuple(ordered_corrections))
