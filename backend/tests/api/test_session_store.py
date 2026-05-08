"""Tests for SessionStoreProtocol implementations."""

from __future__ import annotations

import time

import pytest

from api.middleware.session_store import (
    InMemorySessionStore,
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
        store.save_pkce_state(state="state-1", verifier="ver-1", ttl_seconds=300)
        assert store.pop_pkce_state("state-1") == "ver-1"
        # Popping again returns None (consumed)
        assert store.pop_pkce_state("state-1") is None

    def test_pkce_state_unknown_returns_none(self) -> None:
        store = InMemorySessionStore()
        assert store.pop_pkce_state("never-issued") is None

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
    def store(self, redis_url: str):
        from api.middleware.session_store import RedisSessionStore

        store = RedisSessionStore(redis_url=redis_url, key_prefix="chiliai-test-session:")
        yield store
        # Best-effort cleanup of test keys
        store.flush_test_keys()

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

    def test_pkce_state_round_trip(self, store) -> None:
        store.save_pkce_state(state="redis-state", verifier="redis-ver", ttl_seconds=60)
        assert store.pop_pkce_state("redis-state") == "redis-ver"
        assert store.pop_pkce_state("redis-state") is None
