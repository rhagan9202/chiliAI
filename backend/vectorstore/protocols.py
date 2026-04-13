"""Service-level protocols for the vectorstore module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from vectorstore.service_models import (
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorSearchRequest,
    VectorSearchResponse,
)


@runtime_checkable
class VectorServiceProtocol(Protocol):
    """Service boundary for vector indexing and similarity search."""

    # TODO(production): Add delete and lifecycle methods:
    # - delete(request: VectorDeleteRequest) -> VectorDeleteResponse
    # - get_record(kb_id, record_id) -> VectorRecord | None
    # - count(kb_id) -> int
    # - batch_search(requests: list[VectorSearchRequest]) -> list[VectorSearchResponse]

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]: ...

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse: ...


__all__ = [
    "VectorServiceProtocol",
]