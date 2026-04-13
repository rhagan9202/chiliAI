"""In-memory graph repository for tests and local scaffolding."""

from __future__ import annotations

from graph.adapters.protocols import GraphRepository
from shared.types import Entity, Relationship

__all__ = ["InMemoryGraphRepository"]


class InMemoryGraphRepository(GraphRepository):
    """Persist graph objects in process-local dictionaries keyed by knowledge base."""

    # TODO(production): Add get_entity, delete_entity, get_neighbors, count methods
    # to match the extended GraphRepository protocol. Add referential integrity
    # checks (relationships must reference existing entity IDs). Add property
    # merge logic on upsert (currently blindly overwrites). Add clear(kb_id)
    # for knowledge base teardown.

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Entity]] = {}
        self._relationships: dict[str, dict[str, Relationship]] = {}

    def upsert_entities(self, knowledge_base_id: str, entities: list[Entity]) -> list[Entity]:
        entity_bucket = self._entities.setdefault(knowledge_base_id, {})
        for entity in entities:
            entity_bucket[entity.id] = entity
        return list(entities)

    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
    ) -> list[Relationship]:
        relationship_bucket = self._relationships.setdefault(knowledge_base_id, {})
        for relationship in relationships:
            relationship_bucket[relationship.id] = relationship
        return list(relationships)

    def get_entities(self, knowledge_base_id: str) -> list[Entity]:
        return list(self._entities.get(knowledge_base_id, {}).values())

    def get_relationships(self, knowledge_base_id: str) -> list[Relationship]:
        return list(self._relationships.get(knowledge_base_id, {}).values())