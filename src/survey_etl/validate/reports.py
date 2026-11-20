"""Rows rejected during processing, reported back to the client."""

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from pydantic import PlainSerializer

__all__ = [
    "InvalidRow",
    "IssueReason",
]

type _ReceivedValues = Annotated[
    Mapping[str, object], PlainSerializer(dict, return_type=dict[str, object])
]


class IssueReason(enum.StrEnum):
    """Why a row was dropped."""

    INVALID_VALUE = "invalid_value"
    UNDERAGE = "underage"
    NO_ANSWERS = "no_answers"
    DUPLICATED_ID = "duplicated_id"


@dataclass(frozen=True, slots=True)
class InvalidRow:
    """A rejected row, as it was received, with the reason.

    Attributes:
        row_number: 1-based position of the row in the batch.
        respondent_id: Respondent ID, or None if it was itself invalid.
        values: The row's values as received, read-only.
        reason: Category of the problem.
        details: Human-readable description.
    """

    row_number: int
    respondent_id: int | None
    values: _ReceivedValues
    reason: IssueReason
    details: str

    def __post_init__(self) -> None:
        """Store a read-only copy of the values."""
        object.__setattr__(self, "values", MappingProxyType(dict(self.values)))
