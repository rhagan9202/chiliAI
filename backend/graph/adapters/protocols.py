"""Adapter-level protocols for graph persistence backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.types import Entity, Relationship


@runtime_checkable
class GraphRepository(Protocol):
    """Persist and query graph runtime objects for one knowledge base."""

    # TODO(production): Extend with read/query methods required by the dashboard,
    # investigation workbench, and RAG chat:
    # - get_entity(kb_id, entity_id) -> Entity | None
    # - get_relationship(kb_id, relationship_id) -> Relationship | None
    # - delete_entity(kb_id, entity_id) -> None
    # - delete_relationship(kb_id, relationship_id) -> None
    # - get_neighbors(kb_id, entity_id, depth, direction) -> SubgraphResult
    # - get_entities_by_type(kb_id, entity_type, limit, offset) -> list[Entity]
    # - count_entities(kb_id) -> int / count_relationships(kb_id) -> int
    # - compute_metrics(kb_id) -> GraphMetrics (degree centrality, PageRank)
    # Add pagination (limit/offset or cursor) to get_entities/get_relationships.
    # Add production adapters: Neo4jGraphRepository, MemgraphGraphRepository.
    # See docs/architecture.md §5 graph module.

    def upsert_entities(self, knowledge_base_id: str, entities: list[Entity]) -> list[Entity]: ...

    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
    ) -> list[Relationship]: ...

    def get_entities(self, knowledge_base_id: str) -> list[Entity]: ...

    def get_relationships(self, knowledge_base_id: str) -> list[Relationship]: ...


__all__ = [
    "GraphRepository",
]