"""Session storage protocol and in-memory adapter for the BFF auth flow."""

from __future__ import annotations

import json
from typing import Protocol, cast, runtime_checkable

from pydantic import BaseModel, Field

from api.middleware.exceptions import SessionNotFoundError as SessionNotFoundError


__all__ = [
    "InMemorySessionStore",
    "RedisSessionStore",
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


class RedisSessionStore:
    """Redis-backed session store. Cookie carries opaque ``session_id``.

    Sessions are stored as JSON strings under ``{key_prefix}{sid}`` with a
    Redis ``EX`` matching ``record.ttl_seconds``. PKCE state lives under a
    separate prefix with a short TTL.
    """

    SESSION_PREFIX = "session:"
    PKCE_PREFIX = "pkce:"

    def __init__(self, redis_url: str, *, key_prefix: str = "chiliai:") -> None:
        try:
            import redis
        except ImportError as exc:  # pragma: no cover - guarded by [redis] extra
            raise RuntimeError(
                "RedisSessionStore requires the 'redis' package. "
                "Install with `pip install redis`."
            ) from exc

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix

    def _session_key(self, session_id: str) -> str:
        return f"{self._prefix}{self.SESSION_PREFIX}{session_id}"

    def _pkce_key(self, state: str) -> str:
        return f"{self._prefix}{self.PKCE_PREFIX}{state}"

    def save(self, record: SessionRecord) -> None:
        payload = record.model_dump_json()
        self._client.set(
            self._session_key(record.session_id),
            payload,
            ex=record.ttl_seconds,
        )

    def get(self, session_id: str) -> SessionRecord:
        raw = self._client.get(self._session_key(session_id))
        if raw is None:
            raise SessionNotFoundError(session_id)
        data = json.loads(cast(str, raw))
        return SessionRecord.model_validate(data)

    def delete(self, session_id: str) -> None:
        self._client.delete(self._session_key(session_id))

    def touch(self, session_id: str, *, ttl_seconds: int) -> None:
        record = self.get(session_id)
        updated = record.model_copy(update={"ttl_seconds": ttl_seconds})
        self.save(updated)

    def save_pkce_state(self, *, state: str, verifier: str, ttl_seconds: int) -> None:
        self._client.set(self._pkce_key(state), verifier, ex=ttl_seconds)

    def pop_pkce_state(self, state: str) -> str | None:
        key = self._pkce_key(state)
        with self._client.pipeline() as pipe:
            pipe.get(key)
            pipe.delete(key)
            value, _ = pipe.execute()
        if value is None:
            return None
        return cast(str, value)

    def flush_test_keys(self) -> None:
        """Delete all keys under the configured prefix. Test helper only."""
        pattern = f"{self._prefix}*"
        for key in self._client.scan_iter(match=pattern):
            self._client.delete(key)
