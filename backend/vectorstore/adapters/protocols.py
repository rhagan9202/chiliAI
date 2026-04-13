"""Adapter-level protocols for vectorstore backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vectorstore.models import MetadataValue, VectorMatch, VectorRecord


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Persist embedding records and execute similarity search."""

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