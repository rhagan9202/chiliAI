"""Tests for records domain models and service-boundary models."""

from __future__ import annotations

from records.models import RawRecord, RecordBatch, content_hash_for
from records.service_models import RecordIngestReceipt, RecordSubmission


def _record(record_id: str = "claim-1") -> RawRecord:
    return RawRecord(
        knowledge_base_id="kb-1",
        record_type="claim_record",
        record_id=record_id,
        payload={"claim_id": record_id, "amount": 10.0},
        source_type="file_upload",
        source_ref="claims.csv",
        correlation_id="corr-1",
        content_hash=content_hash_for({"claim_id": record_id, "amount": 10.0}),
    )


def test_content_hash_is_stable_and_order_independent() -> None:
    first = content_hash_for({"a": 1, "b": 2})
    second = content_hash_for({"b": 2, "a": 1})
    assert first == second
    assert first != content_hash_for({"a": 1, "b": 3})


def test_raw_record_carries_all_table_columns() -> None:
    record = _record()
    assert record.knowledge_base_id == "kb-1"
    assert record.record_type == "claim_record"
    assert record.source_type == "file_upload"
    assert record.ingested_at is not None


def test_record_batch_groups_records() -> None:
    batch = RecordBatch(
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        correlation_id="corr-1",
        records=[_record("claim-1"), _record("claim-2")],
    )
    assert len(batch.records) == 2


def test_record_submission_and_receipt() -> None:
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[{"claim_id": "claim-1"}],
        source_type="api_push",
    )
    assert submission.source_ref is None
    receipt = RecordIngestReceipt(
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        correlation_id="corr-1",
        accepted_count=1,
    )
    assert receipt.accepted_count == 1
