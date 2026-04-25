"""In-memory graph repository for tests and local scaffolding."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from copy import deepcopy
from typing import Generator
from typing import Literal

from graph.models import SubgraphResult
from graph.adapters.protocols import GraphRepository
from shared.types import Entity, Relationship

__all__ = ["InMemoryGraphRepository"]


class InMemoryGraphRepository(GraphRepository):
    """Persist graph objects in process-local dictionaries keyed by knowledge base."""

    # TODO(production): Add referential integrity checks (relationships must
    # reference existing entity IDs). Add property merge logic on upsert
    # (currently blindly overwrites). Add clear(kb_id) for knowledge base teardown.

    def __init__(self) -> None:
        self._entities: dict[str, dict[str, Entity]] = {}
        self._relationships: dict[str, dict[str, Relationship]] = {}
        self._outbound_relationships: dict[str, dict[str, list[str]]] = {}
        self._inbound_relationships: dict[str, dict[str, list[str]]] = {}
        self._adjacency_is_stale: set[str] = set()

    def transaction(self, knowledge_base_id: str) -> AbstractContextManager[None]:
        return self._transaction_scope(knowledge_base_id)

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
        self._adjacency_is_stale.add(knowledge_base_id)
        return list(relationships)

    def get_entities(self, knowledge_base_id: str) -> list[Entity]:
        return list(self._entities.get(knowledge_base_id, {}).values())

    def get_relationships(self, knowledge_base_id: str) -> list[Relationship]:
        return list(self._relationships.get(knowledge_base_id, {}).values())

    def get_entity(self, knowledge_base_id: str, entity_id: str) -> Entity | None:
        return self._entities.get(knowledge_base_id, {}).get(entity_id)

    def get_neighbors(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
        direction: Literal["in", "out", "both"],
    ) -> SubgraphResult:
        if direction not in {"in", "out", "both"}:
            msg = "direction must be one of 'in', 'out', or 'both'"
            raise ValueError(msg)

        entity_bucket = self._entities.get(knowledge_base_id, {})
        if entity_id not in entity_bucket:
            return SubgraphResult()

        self._rebuild_adjacency_index_if_needed(knowledge_base_id)

        relationship_bucket = self._relationships.get(knowledge_base_id, {})
        visited_entity_ids: set[str] = {entity_id}
        frontier: set[str] = {entity_id}
        collected_relationship_ids: set[str] = set()

        for _ in range(max(depth, 0)):
            next_frontier: set[str] = set()

            for frontier_entity_id in frontier:
                for relationship_id in self._relationship_ids_for_direction(
                    knowledge_base_id,
                    frontier_entity_id,
                    direction,
                ):
                    relationship = relationship_bucket[relationship_id]
                    collected_relationship_ids.add(relationship.id)

                    if relationship.source_id == frontier_entity_id:
                        next_frontier.add(relationship.target_id)
                    if relationship.target_id == frontier_entity_id:
                        next_frontier.add(relationship.source_id)

            next_frontier -= visited_entity_ids
            visited_entity_ids.update(next_frontier)
            frontier = next_frontier

            if not frontier:
                break

        return SubgraphResult(
            entities=[
                entity_bucket[visited_id]
                for visited_id in visited_entity_ids
                if visited_id in entity_bucket
            ],
            relationships=[
                relationship_bucket[relationship_id]
                for relationship_id in collected_relationship_ids
            ],
        )

    def get_entities_by_type(
        self,
        knowledge_base_id: str,
        entity_type: str,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        if limit <= 0 or offset < 0:
            return []

        matching_entities = [
            entity
            for entity in self.get_entities(knowledge_base_id)
            if entity.type == entity_type
        ]
        return matching_entities[offset : offset + limit]

    def search_entities(
        self,
        knowledge_base_id: str,
        query: str,
        limit: int,
    ) -> list[Entity]:
        if limit <= 0:
            return []

        normalized_query = query.strip().lower()
        if not normalized_query:
            return []

        matches: list[Entity] = []
        for entity in self.get_entities(knowledge_base_id):
            haystacks = [
                property_value
                for property_value in entity.properties.values()
                if isinstance(property_value, str)
            ]
            if any(normalized_query in haystack.lower() for haystack in haystacks):
                matches.append(entity)
            if len(matches) >= limit:
                break
        return matches

    def count_entities(self, knowledge_base_id: str) -> int:
        return len(self._entities.get(knowledge_base_id, {}))

    def count_relationships(self, knowledge_base_id: str) -> int:
        return len(self._relationships.get(knowledge_base_id, {}))

    def delete_entity(self, knowledge_base_id: str, entity_id: str) -> None:
        entity_bucket = self._entities.get(knowledge_base_id, {})
        relationship_bucket = self._relationships.get(knowledge_base_id, {})

        entity_bucket.pop(entity_id, None)

        relationship_ids_to_delete = [
            relationship_id
            for relationship_id, relationship in relationship_bucket.items()
            if relationship.source_id == entity_id or relationship.target_id == entity_id
        ]
        for relationship_id in relationship_ids_to_delete:
            relationship_bucket.pop(relationship_id, None)
        self._adjacency_is_stale.add(knowledge_base_id)

    def delete_relationship(self, knowledge_base_id: str, relationship_id: str) -> None:
        self._relationships.get(knowledge_base_id, {}).pop(relationship_id, None)
        self._adjacency_is_stale.add(knowledge_base_id)

    @contextmanager
    def _transaction_scope(self, knowledge_base_id: str) -> Generator[None, None, None]:
        entities_snapshot = deepcopy(self._entities.get(knowledge_base_id, {}))
        relationships_snapshot = deepcopy(self._relationships.get(knowledge_base_id, {}))

        outbound_snapshot = deepcopy(self._outbound_relationships.get(knowledge_base_id, {}))
        inbound_snapshot = deepcopy(self._inbound_relationships.get(knowledge_base_id, {}))
        adjacency_was_stale = knowledge_base_id in self._adjacency_is_stale
        had_outbound = knowledge_base_id in self._outbound_relationships
        had_inbound = knowledge_base_id in self._inbound_relationships

        try:
            yield
        except Exception:
            self._entities[knowledge_base_id] = entities_snapshot
            self._relationships[knowledge_base_id] = relationships_snapshot

            if had_outbound:
                self._outbound_relationships[knowledge_base_id] = outbound_snapshot
            else:
                self._outbound_relationships.pop(knowledge_base_id, None)

            if had_inbound:
                self._inbound_relationships[knowledge_base_id] = inbound_snapshot
            else:
                self._inbound_relationships.pop(knowledge_base_id, None)

            if adjacency_was_stale:
                self._adjacency_is_stale.add(knowledge_base_id)
            else:
                self._adjacency_is_stale.discard(knowledge_base_id)
            raise

    def _rebuild_adjacency_index_if_needed(self, knowledge_base_id: str) -> None:
        if (
            knowledge_base_id in self._outbound_relationships
            and knowledge_base_id in self._inbound_relationships
            and knowledge_base_id not in self._adjacency_is_stale
        ):
            return

        outbound: dict[str, list[str]] = {}
        inbound: dict[str, list[str]] = {}
        for relationship in self._relationships.get(knowledge_base_id, {}).values():
            outbound.setdefault(relationship.source_id, []).append(relationship.id)
            inbound.setdefault(relationship.target_id, []).append(relationship.id)

        self._outbound_relationships[knowledge_base_id] = outbound
        self._inbound_relationships[knowledge_base_id] = inbound
        self._adjacency_is_stale.discard(knowledge_base_id)

    def _relationship_ids_for_direction(
        self,
        knowledge_base_id: str,
        entity_id: str,
        direction: Literal["in", "out", "both"],
    ) -> list[str]:
        if direction == "in":
            return self._inbound_relationships.get(knowledge_base_id, {}).get(entity_id, [])
        if direction == "out":
            return self._outbound_relationships.get(knowledge_base_id, {}).get(entity_id, [])
        if direction != "both":
            msg = "direction must be one of 'in', 'out', or 'both'"
            raise ValueError(msg)

        return [
            *self._outbound_relationships.get(knowledge_base_id, {}).get(entity_id, []),
            *self._inbound_relationships.get(knowledge_base_id, {}).get(entity_id, []),
        ]