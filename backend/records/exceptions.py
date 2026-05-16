"""Exception hierarchy for the records module."""

from __future__ import annotations


class RecordsError(Exception):
    """Base exception for structured-records ingestion failures."""


class RecordValidationError(RecordsError):
    """Raised when submitted rows fail feed-schema validation or coercion."""


class RecordPersistenceError(RecordsError):
    """Raised when raw records cannot be persisted or read back."""


class RecordFeedNotFoundError(RecordsError):
    """Raised when a submission references a feed not declared in config."""

    def __init__(self, feed_name: str) -> None:
        super().__init__(f"Records feed '{feed_name}' is not declared in the domain config.")
        self.feed_name = feed_name


class RecordMappingError(RecordsError):
    """Raised when a record row cannot be mapped to graph or observation objects."""


__all__ = [
    "RecordFeedNotFoundError",
    "RecordMappingError",
    "RecordPersistenceError",
    "RecordValidationError",
    "RecordsError",
]
