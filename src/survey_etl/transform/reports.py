"""Values changed during transformation, reported back to the client."""

import enum
from dataclasses import dataclass

__all__ = [
    "CorrectedValue",
    "CorrectionReason",
]


class CorrectionReason(enum.StrEnum):
    """Why a value was changed."""

    USAGE_WITHOUT_AWARENESS = "usage_without_awareness"


@dataclass(frozen=True, slots=True)
class CorrectedValue:
    """One value changed during transformation.

    Attributes:
        row_number: 1-based position of the row in the batch.
        respondent_id: Respondent identifier.
        column: Column whose value was changed.
        received: Value before the change.
        corrected: Value after the change.
        reason: Why the value was changed.
    """

    row_number: int
    respondent_id: int
    column: str
    received: int
    corrected: int
    reason: CorrectionReason
