"""Running valid rows through every transformer, in order."""

from collections.abc import Sequence

from survey_etl.survey import LAYOUT, SurveyLayout
from survey_etl.transform.frames import build_frame
from survey_etl.transform.reports import CorrectedValue
from survey_etl.transform.transformers import (
    TRANSFORMERS,
    Transformer,
    TransformOutcome,
)
from survey_etl.validate import ValidRow

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
