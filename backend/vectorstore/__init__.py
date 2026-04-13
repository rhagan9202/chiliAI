"""Public exports for the vectorstore service module."""

from __future__ import annotations

from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.exceptions import VectorDimensionMismatchError, VectorError, VectorStoreError
from vectorstore.models import MetadataValue, VectorMatch, VectorRecord
from vectorstore.protocols import VectorServiceProtocol
from vectorstore.service import VectorService, create_vector_service
from vectorstore.service_models import (
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorIndexSubmission,
    VectorSearchMatch,
    VectorSearchRequest,
    VectorSearchResponse,
)

__all__ = [
    "InMemoryVectorStore",
    "MetadataValue",
    "VectorDimensionMismatchError",
    "VectorError",
    "VectorIndexReceipt",
    "VectorIndexRequest",
    "VectorIndexSubmission",
    "VectorMatch",
    "VectorRecord",
    "VectorSearchMatch",
    "VectorSearchRequest",
    "VectorSearchResponse",
    "VectorService",
    "VectorServiceProtocol",
    "VectorStoreError",
    "VectorStoreProtocol",
    "create_vector_service",
]