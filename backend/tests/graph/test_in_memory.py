"""Tests for the in-memory graph repository."""

from __future__ import annotations

from graph.adapters.in_memory import InMemoryGraphRepository
from shared.types import Entity, Relationship


def test_in_memory_graph_repository_stores_entities_and_relationships() -> None:
    repository = InMemoryGraphRepository()

    repository.upsert_entities(
        "kb-1",
        [Entity(id="entity-1", type="claim", properties={"claim_id": "42"})],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="relationship-1",
                type="submitted_by",
                source_id="entity-1",
                target_id="entity-2",
            )
        ],
    )

    assert [entity.id for entity in repository.get_entities("kb-1")] == ["entity-1"]
    assert [relationship.id for relationship in repository.get_relationships("kb-1")] == [
        "relationship-1"
    ]