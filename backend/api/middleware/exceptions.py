"""Exceptions raised by api.middleware modules."""

from __future__ import annotations

__all__ = [
    "SessionNotFoundError",
    "SessionStoreError",
]


class SessionStoreError(Exception):
    """Base class for session-store failures."""


class SessionNotFoundError(SessionStoreError):
    """Raised when a session id is not present in the store."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"No session registered for session_id={session_id!r}.")
