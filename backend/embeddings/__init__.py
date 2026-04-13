"""Public exports for the embeddings service module."""

from __future__ import annotations

from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.protocols import EmbedderProtocol
from embeddings.exceptions import EmbeddingConfigurationError, EmbeddingError, EmbeddingProviderError
from embeddings.models import EmbeddingItem, EmbeddingMetadata, EmbeddingRequest, EmbeddingResult
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import EmbeddingsService, create_embeddings_service
from embeddings.service_models import (
    EmbedRequest,
    EmbedResponse,
    EmbedSubmission,
    EmbeddedItem,
)

__all__ = [
    "EmbedRequest",
    "EmbedResponse",
    "EmbedSubmission",
    "EmbedderProtocol",
    "EmbeddedItem",
    "EmbeddingConfigurationError",
    "EmbeddingError",
    "EmbeddingItem",
    "EmbeddingMetadata",
    "EmbeddingProviderError",
    "EmbeddingRequest",
    "EmbeddingResult",
    "EmbeddingsService",
    "EmbeddingsServiceProtocol",
    "InMemoryEmbedder",
    "create_embeddings_service",
]