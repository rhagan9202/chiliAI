"""Tests for the Flow 1 worker handler handle_records_ingested."""

from __future__ import annotations

import pytest

from agent.coordinator import handle_records_ingested
from config.schema import (
    RecordEntityMapping,
    RecordFeedConfig,
    RecordObservationMapping,
    RecordRelationshipMapping,
    RecordsConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from monitoring.adapters.in_memory import InMemoryObservationWriter
from records.adapters.in_memory import InMemoryRawRecordStore
from records.exceptions import RecordFeedNotFoundError
from records.models import RawRecord, content_hash_for
from storage.adapters.in_memory import InMemoryObjectStore


def _records_config() -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="claims_feed",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                entities=[
                    RecordEntityMapping(
                        entity_type="claim",
                        id_field="claim_id",
                        property_fields={"amount": "billed_amount"},
                    ),
                    RecordEntityMapping(entity_type="provider", id_field="provider_npi"),
                ],
                relationships=[
                    RecordRelationshipMapping(
                        relationship_type="submitted_by",
                        source_entity_type="claim",
                        target_entity_type="provider",
                    )
                ],
                observations=[
                    RecordObservationMapping(
                        metric_name="claim_anomaly",
                        entity_type="claim",
                        score_field="anomaly_score",
                        rationale="feed score",
                    )
                ],
            )
        ]
    )


def _seed_store(store: InMemoryRawRecordStore, correlation_id: str) -> None:
    payload: dict[str, object] = {
        "claim_id": "c1",
        "provider_npi": "1234567890",
        "billed_amount": 99.0,
        "anomaly_score": 0.8,
    }
    store.persist(
        [
            RawRecord(
                knowledge_base_id="kb-1",
                record_type="claim_record",
                record_id="c1",
                payload=payload,
                source_type="file_upload",
                source_ref="claims.csv",
                correlation_id=correlation_id,
                content_hash=content_hash_for(payload),
            )
        ]
    )


def _graph_service() -> object:
    return create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )


def test_handler_fans_records_out_to_graph_and_observations() -> None:
    store = InMemoryRawRecordStore()
    _seed_store(store, "corr-1")
    graph_service = _graph_service()
    writer = InMemoryObservationWriter()

    processed = handle_records_ingested(
        RecordsIngestedEvent(
            correlation_id="corr-1",
            knowledge_base_id="kb-1",
            feed_name="claims_feed",
            record_type="claim_record",
            record_count=1,
        ),
        records_config=_records_config(),
        raw_record_store=store,
        graph_service=graph_service,  # type: ignore[arg-type]
        observation_writer=writer,
    )

    assert processed == 1
    assert graph_service.get_entity("kb-1", "claim:c1") is not None  # type: ignore[attr-defined]
    assert len(writer.written) == 1
    batch, correlation_id = writer.written[0]
    assert correlation_id == "corr-1"
    assert batch.observations[0].metric_name == "claim_anomaly"


def test_handler_raises_for_unknown_feed() -> None:
    with pytest.raises(RecordFeedNotFoundError):
        handle_records_ingested(
            RecordsIngestedEvent(
                correlation_id="corr-1",
                knowledge_base_id="kb-1",
                feed_name="ghost_feed",
                record_type="claim_record",
                record_count=0,
            ),
            records_config=_records_config(),
            raw_record_store=InMemoryRawRecordStore(),
            graph_service=_graph_service(),  # type: ignore[arg-type]
            observation_writer=InMemoryObservationWriter(),
        )


def test_handler_returns_zero_when_no_records_found() -> None:
    processed = handle_records_ingested(
        RecordsIngestedEvent(
            correlation_id="missing-corr",
            knowledge_base_id="kb-1",
            feed_name="claims_feed",
            record_type="claim_record",
            record_count=0,
        ),
        records_config=_records_config(),
        raw_record_store=InMemoryRawRecordStore(),
        graph_service=_graph_service(),  # type: ignore[arg-type]
        observation_writer=InMemoryObservationWriter(),
    )
    assert processed == 0
