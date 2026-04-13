"""Adapter-level protocols for graph persistence backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from shared.types import Entity, Relationship


@runtime_checkable
class GraphRepository(Protocol):
    """Persist and query graph runtime objects for one knowledge base."""

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