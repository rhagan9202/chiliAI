"""Tests for RecordsService.register_records."""

from __future__ import annotations

import pytest

from config.schema import RecordEntityMapping, RecordFeedConfig, RecordsConfig
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent
from records.adapters.in_memory import InMemoryRawRecordStore
from records.exceptions import RecordFeedNotFoundError, RecordValidationError
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


def test_register_records_rejects_invalid_rows() -> None:
    service = create_records_service(
        InMemoryRawRecordStore(), event_bus=InMemoryEventBus(), records_config=_records_config()
    )
    with pytest.raises(RecordValidationError):
        service.register_records(
            "kb-1",
            RecordSubmission(
                feed_name="claims_feed",
                rows=[{"claim_id": "c1"}],  # missing required "amount"
                source_type="api_push",
            ),
        )
