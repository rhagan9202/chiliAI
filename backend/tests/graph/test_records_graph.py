"""Tests for GraphService.upsert_records_graph (structured-records path)."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import GraphUpdatedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from shared.types import Entity, Relationship
from storage.adapters.in_memory import InMemoryObjectStore


def test_upsert_records_graph_persists_entities_and_relationships() -> None:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    entities = [
        Entity(id="claim:c1", type="claim", properties={"amount": 10.0}),
        Entity(id="provider:p1", type="provider", properties={}),
    ]
    relationships = [
        Relationship(
            id="submitted_by:claim:c1->provider:p1",
            type="submitted_by",
            source_id="claim:c1",
            target_id="provider:p1",
        )
    ]
    stored_entities, stored_relationships = service.upsert_records_graph(
        "kb-1", entities, relationships
    )
    assert {entity.id for entity in stored_entities} == {"claim:c1", "provider:p1"}
    assert [relationship.id for relationship in stored_relationships] == [
        "submitted_by:claim:c1->provider:p1"
    ]
    assert service.get_entity("kb-1", "claim:c1") is not None


def test_upsert_records_graph_publishes_no_graph_updated_event() -> None:
    bus = InMemoryEventBus()
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=bus,
    )
    service.upsert_records_graph(
        "kb-1", [Entity(id="claim:c1", type="claim", properties={})], []
    )
    assert not any(isinstance(e, GraphUpdatedEvent) for e in bus.published_events)


def test_upsert_records_graph_is_idempotent() -> None:
    service = create_graph_service(
        InMemoryGraphRepository(),
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )
    entity = Entity(id="claim:c1", type="claim", properties={})
    service.upsert_records_graph("kb-1", [entity], [])
    service.upsert_records_graph("kb-1", [entity], [])
    assert service.compute_metrics("kb-1").entity_count == 1
