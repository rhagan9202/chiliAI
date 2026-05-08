"""Session storage protocol and in-memory adapter for the BFF auth flow."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from api.middleware.exceptions import SessionNotFoundError as SessionNotFoundError


__all__ = [
    "InMemorySessionStore",
    "SessionNotFoundError",
    "SessionRecord",
    "SessionStoreProtocol",
]


class SessionRecord(BaseModel):
    """Persisted session payload keyed by ``session_id``.

    Tokens are stored server-side; the cookie carries only the opaque id.
    ``access_token_expires_at`` is a Unix timestamp; the auth middleware uses
    it to decide whether to refresh on the current request.
    """

    session_id: str
    user_id: str
    roles: list[str] = Field(default_factory=list)
    email: str | None = None
    access_token: str
    refresh_token: str | None = None
    access_token_expires_at: float
    id_token: str | None = None
    created_at: float
    ttl_seconds: int


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Persist authenticated session payloads keyed by an opaque id."""

    def save(self, record: SessionRecord) -> None: ...
    def get(self, session_id: str) -> SessionRecord: ...
    def delete(self, session_id: str) -> None: ...
    def touch(self, session_id: str, *, ttl_seconds: int) -> None: ...
    def save_pkce_state(self, *, state: str, verifier: str, ttl_seconds: int) -> None: ...
    def pop_pkce_state(self, state: str) -> str | None: ...


class InMemorySessionStore:
    """Thread-naive in-memory session store, intended for tests and dev."""

    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}
        self._pkce: dict[str, str] = {}

    def save(self, record: SessionRecord) -> None:
        self._records[record.session_id] = record

    def get(self, session_id: str) -> SessionRecord:
        record = self._records.get(session_id)
        if record is None:
            raise SessionNotFoundError(session_id)
        return record

    def delete(self, session_id: str) -> None:
        self._records.pop(session_id, None)

    def touch(self, session_id: str, *, ttl_seconds: int) -> None:
        record = self._records.get(session_id)
        if record is None:
            raise SessionNotFoundError(session_id)
        self._records[session_id] = record.model_copy(update={"ttl_seconds": ttl_seconds})

    def save_pkce_state(self, *, state: str, verifier: str, ttl_seconds: int) -> None:
        del ttl_seconds  # InMemory store has no TTL; PKCE state is short-lived per process.
        self._pkce[state] = verifier

    def pop_pkce_state(self, state: str) -> str | None:
        return self._pkce.pop(state, None)
