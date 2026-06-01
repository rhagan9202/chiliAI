"""Tests for graph service read helpers introduced for API-backed investigation views."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from shared.types import Entity, Relationship
from storage.adapters.in_memory import InMemoryObjectStore


def test_graph_service_returns_entity_and_neighbors() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="provider-1", type="provider", properties={"display_name": "Provider 1"}),
            Entity(id="claim-1", type="claim", properties={"display_name": "Claim 1"}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [Relationship(id="rel-1", type="submitted_by", source_id="claim-1", target_id="provider-1")],
    )
    service = create_graph_service(repository, object_store=InMemoryObjectStore(), event_bus=InMemoryEventBus())

    entity = service.get_entity(["kb-1"], "provider-1")
    neighbors, relationships = service.get_neighbors("kb-1", "provider-1")

    assert entity is not None
    assert entity.id == "provider-1"
    assert [neighbor.id for neighbor in neighbors] == ["claim-1"]
    assert [relationship.id for relationship in relationships] == ["rel-1"]


def test_graph_service_get_subgraph_unions_seeds() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(id="provider-1", type="provider", properties={}),
            Entity(id="claim-1", type="claim", properties={}),
            Entity(id="beneficiary-1", type="beneficiary", properties={}),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(id="rel-1", type="submitted_by", source_id="claim-1", target_id="provider-1"),
            Relationship(id="rel-2", type="billed_for", source_id="claim-1", target_id="beneficiary-1"),
        ],
    )
    service = create_graph_service(
        repository, object_store=InMemoryObjectStore(), event_bus=InMemoryEventBus()
    )

    subgraph = service.get_subgraph("kb-1", ["provider-1", "beneficiary-1"], depth=2)

    assert {entity.id for entity in subgraph.entities} == {
        "provider-1",
        "claim-1",
        "beneficiary-1",
    }
    assert {relationship.id for relationship in subgraph.relationships} == {"rel-1", "rel-2"}