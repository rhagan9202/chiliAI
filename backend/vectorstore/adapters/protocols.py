"""Adapter-level protocols for vectorstore backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vectorstore.models import MetadataValue, VectorMatch, VectorRecord


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Persist embedding records and execute similarity search."""

    # TODO(production): Extend with CRUD and lifecycle operations:
    # - delete_records(kb_id, record_ids: list[str]) -> int  (deleted count)
    # - get_record(kb_id, record_id) -> VectorRecord | None
    # - count_records(kb_id) -> int
    # - create_namespace(kb_id) / delete_namespace(kb_id) for KB lifecycle
    # - list_records(kb_id, limit, cursor) -> PaginatedResult  (scroll API)
    # Add hybrid search support (keyword + vector). Add range/list metadata filters.
    # Add production adapters: PgvectorStore, QdrantStore, WeaviateStore.

    def upsert_records(
        self,
        knowledge_base_id: str,
        records: list[VectorRecord],
    ) -> list[VectorRecord]: ...

    def search(
        self,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, MetadataValue] | None = None,
    ) -> list[VectorMatch]: ...


__all__ = [
    "VectorStoreProtocol",
]