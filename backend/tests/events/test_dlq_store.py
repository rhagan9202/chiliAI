"""Tests for the durable DLQ record store (BL-023, events.10)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from database.protocols import ConnectionProvider
from database.runtime import create_connection_provider
from events.adapters.dlq_in_memory import InMemoryDlqRecordStore
from events.adapters.dlq_postgres import PostgresDlqRecordStore
from events.dlq_models import DlqRecord
from shared.utils import utc_now

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _record(dlq_id: str, *, event_type: str = "documents.uploaded") -> DlqRecord:
    return DlqRecord(
        dlq_id=dlq_id,
        event_type=event_type,
        correlation_id=f"corr-{dlq_id}",
        payload={"event_type": event_type, "event_body": "{}"},
        error_message="boom",
        error_traceback="Traceback: boom",
        retry_count=3,
        failed_at=utc_now(),
        created_at=utc_now(),
    )


def test_persist_and_get_roundtrip() -> None:
    store = InMemoryDlqRecordStore()
    stored = store.persist(_record("d-1"))
    assert stored.status == "pending"
    fetched = store.get("d-1")
    assert fetched is not None
    assert fetched.error_message == "boom"
    assert store.get("missing") is None


def test_list_filters_and_paginates_newest_first() -> None:
    store = InMemoryDlqRecordStore()
    for i in range(5):
        store.persist(_record(f"d-{i}", event_type="a.x" if i % 2 == 0 else "b.y"))
    items, total = store.list(event_type="a.x")
    assert total == 3
    assert [r.dlq_id for r in items] == ["d-4", "d-2", "d-0"]  # newest first
    page, total = store.list(limit=2, offset=1)
    assert total == 5
    assert len(page) == 2


def test_mark_replayed_is_cas_on_pending() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1"))
    updated = store.mark_replayed("d-1")
    assert updated is not None
    assert updated.status == "replayed"
    assert updated.replayed_at is not None
    assert store.mark_replayed("d-1") is None       # already replayed
    assert store.mark_discarded("d-1") is None      # not pending anymore
    assert store.mark_replayed("missing") is None


def test_mark_discarded_is_cas_on_pending() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1"))
    updated = store.mark_discarded("d-1")
    assert updated is not None
    assert updated.status == "discarded"
    assert updated.replayed_at is None
    assert store.mark_replayed("d-1") is None
    assert store.mark_discarded("d-1") is None  # already discarded


def test_list_status_filter() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1"))
    store.persist(_record("d-2"))
    store.mark_discarded("d-1")
    pending, total = store.list(status="pending")
    assert total == 1 and pending[0].dlq_id == "d-2"


def test_persist_is_upsert_by_id() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1", event_type="a.x"))
    updated = _record("d-1", event_type="b.y")
    store.persist(updated)
    items, total = store.list()
    assert total == 1
    assert items[0].event_type == "b.y"


@pytest.fixture
def database_url() -> str:
    """Return the test database DSN, skipping the test when it is unset."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping DLQ store integration test.")
    return url


@pytest.mark.integration
class TestPostgresDlqRecordStore:
    """Integration tests against a live Postgres DB (BL-023, events.10)."""

    @pytest.fixture
    def provider(self, database_url: str) -> Iterator[ConnectionProvider]:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=_BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": database_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        connection_provider = create_connection_provider(
            DatabaseConfig(backend="postgres")
        )
        assert connection_provider is not None
        with connection_provider.connection() as conn:
            conn.execute("DELETE FROM event_dlq")
            conn.commit()
        yield connection_provider
        connection_provider.close()

    def test_roundtrip_and_cas(self, provider: ConnectionProvider) -> None:
        store = PostgresDlqRecordStore(provider)
        record = _record("pg-d-1")
        store.persist(record)
        fetched = store.get("pg-d-1")
        assert fetched is not None
        assert fetched.payload == record.payload
        assert fetched.status == "pending"
        assert store.mark_replayed("pg-d-1") is not None
        assert store.mark_replayed("pg-d-1") is None  # CAS: already replayed
        assert store.mark_discarded("pg-d-1") is None

    def test_persist_is_upsert_by_id(self, provider: ConnectionProvider) -> None:
        store = PostgresDlqRecordStore(provider)
        store.persist(_record("pg-d-2", event_type="a.x"))
        updated = _record("pg-d-2", event_type="b.y")
        store.persist(updated)
        items, total = store.list()
        assert total == 1
        assert items[0].event_type == "b.y"

    def test_list_filters_and_total(self, provider: ConnectionProvider) -> None:
        store = PostgresDlqRecordStore(provider)
        for i in range(3):
            store.persist(_record(f"pg-l-{i}", event_type="x.y"))
        items, total = store.list(event_type="x.y", limit=2)
        assert total >= 3
        assert len(items) == 2
        assert items[0].created_at >= items[1].created_at  # newest first
