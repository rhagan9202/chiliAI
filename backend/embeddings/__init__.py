"""Public exports for the embeddings service module."""

from __future__ import annotations

from embeddings.adapters.cache_in_memory import (
    InMemoryLruEmbeddingCache,
    create_embedding_cache,
    embedding_cache_namespace,
)
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.adapters.openai_adapter import OpenAIEmbedder
from embeddings.adapters.protocols import (
    EmbedderProtocol,
    EmbeddingCacheProtocol,
    GraphEmbeddingProviderProtocol,
)
from embeddings.adapters.sentence_transformers_adapter import (
    SentenceTransformersEmbedder,
)
from embeddings.exceptions import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProviderError,
)
from embeddings.models import (
    build_embedding_cache_key,
    CachedEmbedding,
    EmbeddingChannel,
    EmbeddingItem,
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
    EmbeddingVector,
    GraphEmbeddingBatch,
    GraphEmbeddingStatus,
)
from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service import EmbeddingsService, create_embeddings_service
from embeddings.service_models import (
    EmbedRequest,
    EmbedResponse,
    EmbedSubmission,
    EmbeddedItem,
)

__all__ = [
    "CachedEmbedding",
    "EmbedRequest",
    "EmbedResponse",
    "EmbedSubmission",
    "EmbedderProtocol",
    "EmbeddedItem",
    "EmbeddingCacheProtocol",
    "EmbeddingChannel",
    "EmbeddingConfigurationError",
    "EmbeddingError",
    "EmbeddingItem",
    "EmbeddingMetadata",
    "EmbeddingProviderError",
    "EmbeddingRequest",
    "EmbeddingResult",
    "EmbeddingVector",
    "EmbeddingsService",
    "EmbeddingsServiceProtocol",
    "GraphEmbeddingBatch",
    "GraphEmbeddingProviderProtocol",
    "GraphEmbeddingStatus",
    "InMemoryEmbedder",
    "InMemoryLruEmbeddingCache",
    "OpenAIEmbedder",
    "SentenceTransformersEmbedder",
    "build_embedding_cache_key",
    "create_embedding_cache",
    "create_embeddings_service",
    "embedding_cache_namespace",
]
