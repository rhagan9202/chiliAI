"""Adapter-level protocols for graph persistence backends."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Literal, Protocol, runtime_checkable

from graph.models import SubgraphResult
from shared.types import Entity, Relationship


@runtime_checkable
class GraphRepository(Protocol):
    """Persist and query graph runtime objects for one knowledge base."""

    # TODO(production): Extend with additional graph reads required by the dashboard,
    # investigation workbench, and RAG chat:
    # - get_relationship(kb_id, relationship_id) -> Relationship | None
    # - compute_metrics(kb_id) -> GraphMetrics (degree centrality, PageRank)
    # Add pagination (limit/offset or cursor) to get_entities/get_relationships.
    # Add production adapters: Neo4jGraphRepository, MemgraphGraphRepository.
    # See docs/architecture.md §5 graph module.

    def upsert_entities(self, knowledge_base_id: str, entities: list[Entity]) -> list[Entity]: ...

    def transaction(self, knowledge_base_id: str) -> AbstractContextManager[None]: ...

    def upsert_relationships(
        self,
        knowledge_base_id: str,
        relationships: list[Relationship],
    ) -> list[Relationship]: ...

    def get_entities(self, knowledge_base_id: str) -> list[Entity]: ...

    def get_relationships(self, knowledge_base_id: str) -> list[Relationship]: ...

    def get_entity(self, knowledge_base_id: str, entity_id: str) -> Entity | None: ...

    def update_entity_properties(
        self,
        knowledge_base_id: str,
        entity_id: str,
        properties: dict[str, object],
    ) -> Entity: ...

    def get_neighbors(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
        direction: Literal["in", "out", "both"],
    ) -> SubgraphResult: ...

    def get_entities_by_type(
        self,
        knowledge_base_id: str,
        entity_type: str,
        limit: int,
        offset: int,
    ) -> list[Entity]: ...

    def search_entities(
        self,
        knowledge_base_id: str,
        query: str,
        limit: int,
    ) -> list[Entity]: ...

    def count_entities(self, knowledge_base_id: str) -> int: ...

    def count_relationships(self, knowledge_base_id: str) -> int: ...

    def delete_knowledge_base(self, knowledge_base_id: str) -> None: ...

    def delete_entity(self, knowledge_base_id: str, entity_id: str) -> None: ...

    def delete_relationship(self, knowledge_base_id: str, relationship_id: str) -> None: ...


__all__ = [
    "GraphRepository",
]