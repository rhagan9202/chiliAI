"""Tests for the in-memory raw record store."""

from __future__ import annotations

from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.protocols import RawRecordStore
from records.models import RawRecord, content_hash_for


def _record(record_id: str, *, correlation_id: str = "corr-1") -> RawRecord:
    payload: dict[str, object] = {"claim_id": record_id}
    return RawRecord(
        knowledge_base_id="kb-1",
        record_type="claim_record",
        record_id=record_id,
        payload=payload,
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id=correlation_id,
        content_hash=content_hash_for(payload),
    )


def test_store_satisfies_protocol() -> None:
    store: RawRecordStore = InMemoryRawRecordStore()
    assert store.persist([]) == 0


def test_persist_counts_only_new_rows() -> None:
    store = InMemoryRawRecordStore()
    assert store.persist([_record("c1"), _record("c2")]) == 2
    # Re-persisting the same primary keys inserts nothing (idempotency).
    assert store.persist([_record("c1")]) == 0


def test_load_batch_filters_by_correlation_id() -> None:
    store = InMemoryRawRecordStore()
    store.persist([_record("c1", correlation_id="corr-1")])
    store.persist([_record("c2", correlation_id="corr-2")])
    loaded = store.load_batch(knowledge_base_id="kb-1", correlation_id="corr-1")
    assert [record.record_id for record in loaded] == ["c1"]
