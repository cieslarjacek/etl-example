"""Errors raised by the survey database."""

__all__ = [
    "RespondentConflictError",
    "SummaryNotFoundError",
]


class RespondentConflictError(RuntimeError):
    """A respondent ID being stored is already in the database."""

    def __init__(self, database_message: str) -> None:
        """Store the database's description of the conflict.

        Args:
            database_message: Message of the database driver.
        """
        super().__init__(database_message)
        self.database_message = database_message

    def __str__(self) -> str:
        """Explain the conflict and what was stored."""
        return (
            "respondent ID already stored, nothing from this batch was "
            f"saved ({self.database_message})"
        )


class SummaryNotFoundError(LookupError):
    """No stored summary matches the selected waves and categories."""

    def __str__(self) -> str:
        """Explain that the selection matched nothing."""
        return (
            "no stored summary matches the selected waves and age categories"
        )
