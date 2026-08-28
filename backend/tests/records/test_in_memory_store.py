"""Tests for the in-memory raw record store."""

from __future__ import annotations

from records.adapters.in_memory import InMemoryRawRecordStore
from records.adapters.protocols import RawRecordStore
from records.models import RawRecord, RawRecordKey, content_hash_for


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
    assert store.persist([]) == []


def test_persist_returns_only_the_keys_it_inserted() -> None:
    store = InMemoryRawRecordStore()
    assert store.persist([_record("c1"), _record("c2")]) == [
        RawRecordKey("claim_record", "c1"),
        RawRecordKey("claim_record", "c2"),
    ]
    # Re-persisting the same primary keys inserts nothing (idempotency), so
    # those rows are not this call's to roll back.
    assert store.persist([_record("c1")]) == []


def test_delete_records_removes_only_the_named_keys() -> None:
    store = InMemoryRawRecordStore()
    store.persist([_record("c1", correlation_id="corr-shared")])
    store.persist([_record("c2", correlation_id="corr-shared")])

    removed = store.delete_records(
        knowledge_base_id="kb-1", keys=[RawRecordKey("claim_record", "c2")]
    )

    assert removed == 1
    assert [
        record.record_id
        for record in store.load_batch(
            knowledge_base_id="kb-1", correlation_id="corr-shared"
        )
    ] == ["c1"]


def test_load_batch_filters_by_correlation_id() -> None:
    store = InMemoryRawRecordStore()
    store.persist([_record("c1", correlation_id="corr-1")])
    store.persist([_record("c2", correlation_id="corr-2")])
    loaded = store.load_batch(knowledge_base_id="kb-1", correlation_id="corr-1")
    assert [record.record_id for record in loaded] == ["c1"]


def test_load_for_kb_returns_all_kb_records_sorted() -> None:
    store = InMemoryRawRecordStore()
    store.persist([_record("c2", correlation_id="corr-1")])
    store.persist([_record("c1", correlation_id="corr-2")])
    store.persist(
        [
            RawRecord(
                knowledge_base_id="kb-other",
                record_type="claim_record",
                record_id="c9",
                payload={"claim_id": "c9"},
                source_type="file_upload",
                source_ref=None,
                correlation_id="corr-3",
                content_hash=content_hash_for({"claim_id": "c9"}),
            )
        ]
    )

    loaded = store.load_for_kb(knowledge_base_id="kb-1")

    # All correlation batches for the KB, deterministic order, other KBs excluded.
    assert [record.record_id for record in loaded] == ["c1", "c2"]


def test_submission_dedup_round_trip() -> None:
    store = InMemoryRawRecordStore()
    assert (
        store.was_submitted(knowledge_base_id="kb-1", submission_hash="sub-1") is False
    )
    store.record_submission(
        knowledge_base_id="kb-1", submission_hash="sub-1", correlation_id="corr-1"
    )
    assert store.was_submitted(knowledge_base_id="kb-1", submission_hash="sub-1") is True


def test_submission_dedup_is_scoped_by_kb_and_hash() -> None:
    store = InMemoryRawRecordStore()
    store.record_submission(
        knowledge_base_id="kb-1", submission_hash="sub-1", correlation_id="corr-1"
    )
    # Different KB, same hash → not seen.
    assert (
        store.was_submitted(knowledge_base_id="kb-2", submission_hash="sub-1") is False
    )
    # Same KB, different hash → not seen.
    assert (
        store.was_submitted(knowledge_base_id="kb-1", submission_hash="sub-2") is False
    )


def test_delete_by_kb_clears_submissions_and_records() -> None:
    """delete_by_kb removes both raw_records and submission hashes for the KB."""
    store = InMemoryRawRecordStore()
    store.record_submission(
        knowledge_base_id="kb-del", submission_hash="sub-del", correlation_id="corr-del"
    )
    store.persist([
        RawRecord(
            knowledge_base_id="kb-del",
            record_type="claim_record",
            record_id="r1",
            payload={"claim_id": "r1"},
            source_type="file_upload",
            source_ref=None,
            correlation_id="corr-del",
            content_hash=content_hash_for({"claim_id": "r1"}),
        )
    ])

    removed = store.delete_by_kb("kb-del")

    assert removed == 1
    assert store.was_submitted(knowledge_base_id="kb-del", submission_hash="sub-del") is False
    assert store.load_batch(knowledge_base_id="kb-del", correlation_id="corr-del") == []


def test_delete_by_kb_isolates_other_kbs() -> None:
    """delete_by_kb must not touch records or submissions belonging to other KBs."""
    store = InMemoryRawRecordStore()

    # KB to be deleted.
    store.record_submission(
        knowledge_base_id="kb-del", submission_hash="sub-del", correlation_id="corr-del"
    )
    store.persist([
        RawRecord(
            knowledge_base_id="kb-del",
            record_type="claim_record",
            record_id="r-del",
            payload={"claim_id": "r-del"},
            source_type="file_upload",
            source_ref=None,
            correlation_id="corr-del",
            content_hash=content_hash_for({"claim_id": "r-del"}),
        )
    ])

    # KB that should survive.
    store.record_submission(
        knowledge_base_id="kb-keep", submission_hash="sub-keep", correlation_id="corr-keep"
    )
    store.persist([
        RawRecord(
            knowledge_base_id="kb-keep",
            record_type="claim_record",
            record_id="r-keep",
            payload={"claim_id": "r-keep"},
            source_type="file_upload",
            source_ref=None,
            correlation_id="corr-keep",
            content_hash=content_hash_for({"claim_id": "r-keep"}),
        )
    ])

    store.delete_by_kb("kb-del")

    # Surviving KB's data is intact.
    assert store.was_submitted(knowledge_base_id="kb-keep", submission_hash="sub-keep") is True
    assert len(store.load_batch(knowledge_base_id="kb-keep", correlation_id="corr-keep")) == 1
