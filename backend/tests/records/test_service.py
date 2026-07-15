"""Tests for RecordsService.register_records."""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from config.schema import RecordEntityMapping, RecordFeedConfig, RecordsConfig
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent
from records.adapters.in_memory import InMemoryRawRecordStore
from records.exceptions import RecordFeedNotFoundError
from records.service import create_records_service
from records.service_models import RecordSubmission
from shared.types import PropertyDefinition, PropertyType


def _records_config() -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="claims_feed",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                record_schema={
                    "claim_id": PropertyDefinition(
                        type=PropertyType.STRING, display="Claim ID", required=True
                    ),
                    "amount": PropertyDefinition(
                        type=PropertyType.DECIMAL, display="Amount", required=True
                    ),
                },
                entities=[RecordEntityMapping(entity_type="claim", id_field="claim_id")],
            )
        ]
    )


def test_register_records_persists_publishes_and_receipts() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    receipt = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "10"}, {"claim_id": "c2", "amount": "20"}],
            source_type="file_upload",
            source_ref="claims.csv",
        ),
    )

    assert receipt.accepted_count == 2
    assert receipt.record_type == "claim_record"
    persisted = store.load_batch(
        knowledge_base_id="kb-1", correlation_id=receipt.correlation_id
    )
    assert {record.record_id for record in persisted} == {"c1", "c2"}
    assert persisted[0].payload["amount"] == 10.0  # coerced from "10"

    published = [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)]
    assert len(published) == 1
    assert published[0].correlation_id == receipt.correlation_id
    assert published[0].record_count == 2


def test_register_records_rejects_unknown_feed() -> None:
    service = create_records_service(
        InMemoryRawRecordStore(), event_bus=InMemoryEventBus(), records_config=_records_config()
    )
    with pytest.raises(RecordFeedNotFoundError):
        service.register_records(
            "kb-1",
            RecordSubmission(feed_name="ghost_feed", rows=[{}], source_type="api_push"),
        )


def test_register_records_does_not_publish_event_when_no_new_records() -> None:
    store = InMemoryRawRecordStore()
    event_bus = InMemoryEventBus()
    service = create_records_service(
        store,
        event_bus=event_bus,
        records_config=_records_config(),
    )
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[
            {
                "claim_id": "claim-1",
                "amount": "100",
            }
        ],
        source_type="api_push",
        source_ref=None,
    )

    first = service.register_records("kb-1", submission)
    second = service.register_records("kb-1", submission)

    assert first.accepted_count == 1
    assert second.accepted_count == 0
    assert [event.event_type for event in event_bus.published_events] == ["records.ingested"]


def test_register_records_uses_id_template() -> None:
    """When a feed declares id_template, record_id is the interpolated composite key."""
    config = RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="segmented_feed",
                record_type="seg_record",
                source="file_upload",
                id_field="CLM_ID",
                id_template="{CLM_ID}:{SEGMENT}",
                record_schema={
                    "CLM_ID": PropertyDefinition(
                        type=PropertyType.STRING, display="Claim ID", required=True
                    ),
                    "SEGMENT": PropertyDefinition(
                        type=PropertyType.STRING, display="Segment", required=True
                    ),
                },
            )
        ]
    )
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=config)
    receipt = service.register_records(
        "kb-seg",
        RecordSubmission(
            feed_name="segmented_feed",
            rows=[
                {"CLM_ID": "CLM001", "SEGMENT": "1"},
                {"CLM_ID": "CLM001", "SEGMENT": "2"},
            ],
            source_type="file_upload",
            source_ref="seg.csv",
        ),
    )
    assert receipt.accepted_count == 2
    persisted = store.load_batch(knowledge_base_id="kb-seg", correlation_id=receipt.correlation_id)
    record_ids = {r.record_id for r in persisted}
    assert record_ids == {"CLM001:1", "CLM001:2"}


def test_register_records_partitions_invalid_rows_without_raising() -> None:
    """A bad row is reported, not raised; valid rows still ingest (BL-015)."""
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    receipt = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[
                {"claim_id": "c1", "amount": "10"},
                {"claim_id": "c2"},  # missing required "amount"
            ],
            source_type="api_push",
        ),
    )

    assert receipt.accepted_count == 1
    assert receipt.rejected_count == 1
    assert [r.index for r in receipt.rejected] == [1]
    assert receipt.duplicate is False
    persisted = store.load_batch(
        knowledge_base_id="kb-1", correlation_id=receipt.correlation_id
    )
    assert {r.record_id for r in persisted} == {"c1"}


def test_register_records_all_rows_rejected_does_not_publish() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    receipt = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1"}],  # missing required "amount"
            source_type="api_push",
        ),
    )

    assert receipt.accepted_count == 0
    assert receipt.rejected_count == 1
    assert receipt.duplicate is False
    assert [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)] == []


def test_register_records_dedupes_identical_resubmission() -> None:
    """A re-pushed identical batch is a no-op flagged duplicate (BL-015)."""
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[{"claim_id": "c1", "amount": "10"}, {"claim_id": "c2", "amount": "20"}],
        source_type="api_push",
    )

    first = service.register_records("kb-1", submission)
    second = service.register_records("kb-1", submission)

    assert first.duplicate is False
    assert first.accepted_count == 2
    assert second.duplicate is True
    assert second.accepted_count == 0
    assert second.duplicate_count == 2
    # No second persistence and no second event.
    published = [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)]
    assert len(published) == 1


def test_register_records_dedup_is_row_order_independent() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    first = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "10"}, {"claim_id": "c2", "amount": "20"}],
            source_type="api_push",
        ),
    )
    # Same rows, reversed order → same submission hash → duplicate.
    second = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c2", "amount": "20"}, {"claim_id": "c1", "amount": "10"}],
            source_type="api_push",
        ),
    )

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.accepted_count == 0


def test_register_records_duplicate_increments_dedup_counter() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(
        store, event_bus=bus, records_config=_records_config()
    )
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[{"claim_id": "c-dedup-1", "amount": "10"}],
        source_type="api_push",
    )
    labels = {"kind": "record_batch"}

    first = service.register_records("kb-dedup", submission)
    baseline = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    second = service.register_records("kb-dedup", submission)

    assert first.duplicate is False
    assert second.duplicate is True
    after = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    assert after == baseline + 1.0
