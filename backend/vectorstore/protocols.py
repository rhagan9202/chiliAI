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

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]: ...

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse: ...