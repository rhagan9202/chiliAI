"""Exception hierarchy for the embeddings module."""

from __future__ import annotations


class EmbeddingError(Exception):
    """Base exception for embeddings module failures."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when an embedding request is invalid or incomplete."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when the configured embedder cannot produce vectors."""


__all__ = [
    "EmbeddingConfigurationError",
    "EmbeddingError",
    "EmbeddingProviderError",
]