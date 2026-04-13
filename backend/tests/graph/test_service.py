"""Tests for the graph service."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import GraphUpdatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from graph.service_models import GraphBuildTask
from shared.types import Entity, Relationship
from storage.adapters.in_memory import InMemoryObjectStore


def test_graph_service_upserts_and_publishes_update() -> None:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=object_store,
        event_bus=event_bus,
    )

    receipt = service.upsert_task(
        GraphBuildTask(
            knowledge_base_id="kb-1",
            source_document_id="doc-1",
            parsed_document_id="parsed-1",
            extraction_result_id="extract-1",
            validation_report_id="validate-1",
            validation_storage_key="knowledgebases/kb-1/validations/extract-1.json",
            entities=[
                Entity(id="entity-1", type="claim", properties={"claim_id": "42"}),
                Entity(id="entity-2", type="provider", properties={"npi": "1234567890"}),
            ],
            relationships=[
                Relationship(
                    id="relationship-1",
                    type="submitted_by",
                    source_id="entity-1",
                    target_id="entity-2",
                )
            ],
        )
    )

    assert receipt.graph_update_storage_key == "knowledgebases/kb-1/graph_updates/extract-1.json"
    assert receipt.upserted_entity_count == 2
    assert receipt.upserted_relationship_count == 1
    assert isinstance(event_bus.published_events[-1], GraphUpdatedEvent)

    stored = object_store.get_bytes(receipt.graph_update_storage_key)
    assert b'"validation_report_id":"validate-1"' in stored.content