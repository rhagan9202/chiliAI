"""Exception hierarchy for the events module."""

from __future__ import annotations


class EventsError(Exception):
    """Base exception for the events module."""


class DlqPersistenceError(EventsError):
    """Raised when a DLQ record cannot be persisted or read back."""


__all__ = ["DlqPersistenceError", "EventsError"]
