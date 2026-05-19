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

    def get_record(
        self,
        knowledge_base_id: str,
        record_id: str,
    ) -> VectorRecord | None: ...

    def count_records(self, knowledge_base_id: str) -> int: ...

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool: ...

    def delete_namespace(self, knowledge_base_id: str) -> int: ...


__all__ = [
    "VectorStoreProtocol",
]
