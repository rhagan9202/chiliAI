"""Tests for SessionStoreProtocol implementations."""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from api.middleware.session_store import (
    InMemorySessionStore,
    RedisSessionStore,
    SessionNotFoundError,
    SessionRecord,
)


def _record(sid: str = "sid-1", *, ttl: int = 3600) -> SessionRecord:
    now = time.time()
    return SessionRecord(
        session_id=sid,
        user_id="user-42",
        roles=["analyst"],
        email="user@example.com",
        access_token="access-abc",
        refresh_token="refresh-xyz",
        access_token_expires_at=now + 600,
        id_token="id-tok",
        created_at=now,
        ttl_seconds=ttl,
    )


class TestInMemorySessionStore:
    def test_save_and_get_round_trip(self) -> None:
        store = InMemorySessionStore()
        record = _record()
        store.save(record)
        assert store.get("sid-1") == record
        assert store.get("sid-1").access_token == "access-abc"

    def test_get_missing_session_raises(self) -> None:
        store = InMemorySessionStore()
        with pytest.raises(SessionNotFoundError):
            store.get("missing")

    def test_delete_removes_session(self) -> None:
        store = InMemorySessionStore()
        store.save(_record())
        store.delete("sid-1")
        with pytest.raises(SessionNotFoundError):
            store.get("sid-1")

    def test_delete_missing_session_is_idempotent(self) -> None:
        store = InMemorySessionStore()
        store.delete("never-existed")  # no raise

    def test_touch_extends_ttl(self) -> None:
        store = InMemorySessionStore()
        store.save(_record(ttl=60))
        store.touch("sid-1", ttl_seconds=3600)
        record = store.get("sid-1")
        assert record.ttl_seconds == 3600
        assert record.access_token == "access-abc"

    def test_touch_missing_session_raises(self) -> None:
        store = InMemorySessionStore()
        with pytest.raises(SessionNotFoundError):
            store.touch("missing", ttl_seconds=60)

    def test_save_replaces_existing_record(self) -> None:
        store = InMemorySessionStore()
        store.save(_record())
        replacement = SessionRecord(
            session_id="sid-1",
            user_id="user-42",
            roles=["admin"],
            email="user@example.com",
            access_token="new-access",
            refresh_token="new-refresh",
            access_token_expires_at=time.time() + 600,
            id_token="id-tok",
            created_at=time.time(),
            ttl_seconds=3600,
        )
        store.save(replacement)
        assert store.get("sid-1").access_token == "new-access"

    def test_pkce_state_pop_consumes_and_returns_none_on_repeat(self) -> None:
        store = InMemorySessionStore()
        store.save_pkce_state(state="state-1", verifier="ver-1", ttl_seconds=300, nonce="nonce-1")
        popped = store.pop_pkce_state("state-1")
        assert popped is not None
        assert popped.verifier == "ver-1"
        assert popped.nonce == "nonce-1"
        # Popping again returns None (consumed)
        assert store.pop_pkce_state("state-1") is None

    def test_pkce_state_unknown_returns_none(self) -> None:
        store = InMemorySessionStore()
        assert store.pop_pkce_state("never-issued") is None

    def test_pkce_state_roundtrips_nonce(self) -> None:
        store = InMemorySessionStore()
        store.save_pkce_state(state="s1", verifier="v1", ttl_seconds=60, nonce="n1")
        popped = store.pop_pkce_state("s1")
        assert popped is not None
        assert popped.verifier == "v1"
        assert popped.nonce == "n1"
        assert store.pop_pkce_state("s1") is None  # pop is one-shot

    def test_session_not_found_error_carries_session_id(self) -> None:
        with pytest.raises(SessionNotFoundError) as excinfo:
            InMemorySessionStore().get("sid-missing")
        assert excinfo.value.session_id == "sid-missing"


@pytest.mark.integration
class TestRedisSessionStore:
    """Integration tests for RedisSessionStore. Requires CHILI_TEST_REDIS_URL."""

    @pytest.fixture
    def redis_url(self) -> str:
        import os

        url = os.environ.get("CHILI_TEST_REDIS_URL")
        if url is None:
            pytest.skip("CHILI_TEST_REDIS_URL is not set; skipping integration test.")
        return url

    @pytest.fixture
    def store(self, redis_url: str) -> Iterator[RedisSessionStore]:
        store = RedisSessionStore(redis_url=redis_url, key_prefix="chiliai-test-session:")
        yield store
        # Cleanup: drop all keys this test fixture created.
        keys = list(store._client.scan_iter(match=f"{store._prefix}*"))
        if keys:
            store._client.delete(*keys)

    def test_save_get_round_trip(self, store) -> None:
        record = _record(sid="redis-sid-1")
        store.save(record)
        loaded = store.get("redis-sid-1")
        assert loaded.user_id == "user-42"
        assert loaded.roles == ["analyst"]
        assert loaded.access_token == "access-abc"

    def test_get_missing_raises(self, store) -> None:
        with pytest.raises(SessionNotFoundError):
            store.get("redis-missing")

    def test_delete_removes_session(self, store) -> None:
        store.save(_record(sid="redis-sid-2"))
        store.delete("redis-sid-2")
        with pytest.raises(SessionNotFoundError):
            store.get("redis-sid-2")

    def test_pkce_state_round_trip(self, store: RedisSessionStore) -> None:
        store.save_pkce_state(
            state="redis-state", verifier="redis-ver", ttl_seconds=60, nonce="redis-nonce"
        )
        popped = store.pop_pkce_state("redis-state")
        assert popped is not None
        assert popped.verifier == "redis-ver"
        assert popped.nonce == "redis-nonce"
        assert store.pop_pkce_state("redis-state") is None

    def test_legacy_bare_string_pkce_record_fails_closed(self, store: RedisSessionStore) -> None:
        # Simulate a record written by a pre-BL-022 deployment: a bare verifier
        # string, not the PkceState JSON envelope. pop_pkce_state must fail
        # closed (return None) rather than crash or return unvalidated data.
        raw_key = store._pkce_key("legacy-state")
        store._client.set(raw_key, "bare-verifier-string", ex=60)
        assert store.pop_pkce_state("legacy-state") is None

    def test_touch_extends_ttl(self, store: RedisSessionStore) -> None:
        record = _record(sid="redis-touch", ttl=60)
        store.save(record)
        store.touch("redis-touch", ttl_seconds=3600)
        refreshed = store.get("redis-touch")
        assert refreshed.ttl_seconds == 3600
        assert refreshed.access_token == "access-abc"
