"""Tests for the durable DLQ record store (BL-023, events.10)."""

from __future__ import annotations

from events.adapters.dlq_in_memory import InMemoryDlqRecordStore
from events.dlq_models import DlqRecord
from shared.utils import utc_now


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


def test_list_status_filter() -> None:
    store = InMemoryDlqRecordStore()
    store.persist(_record("d-1"))
    store.persist(_record("d-2"))
    store.mark_discarded("d-1")
    pending, total = store.list(status="pending")
    assert total == 1 and pending[0].dlq_id == "d-2"
