"""Service-level protocols for the vectorstore module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vectorstore.models import VectorRecord
from vectorstore.service_models import (
    VectorDeleteResponse,
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorSearchRequest,
    VectorSearchResponse,
)


@runtime_checkable
class VectorServiceProtocol(Protocol):
    """Service boundary for vector indexing, search, and lifecycle operations."""

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]: ...

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse: ...

    def batch_search(
        self, requests: list[VectorSearchRequest]
    ) -> list[VectorSearchResponse]: ...

    def get_record(
        self, knowledge_base_id: str, record_id: str
    ) -> VectorRecord | None: ...

    def count(self, knowledge_base_id: str) -> int: ...

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool: ...

    def delete_knowledge_base(self, knowledge_base_id: str) -> VectorDeleteResponse: ...

    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> VectorDeleteResponse: ...


__all__ = [
    "VectorServiceProtocol",
]
