"""Adapter-level protocols for embedding providers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from embeddings.models import EmbeddingRequest, EmbeddingResult


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Generate vectors from embedding requests."""

    # TODO(production): Extend protocol with model introspection and health methods:
    # - get_model_info() -> EmbeddingModelInfo (name, dimensions, max tokens, provider)
    # - health_check() -> bool
    # Add async variant for non-blocking embedding in pipeline workers.
    # Implement production adapters: OpenAIEmbedder, SentenceTransformersEmbedder.
    # See docs/architecture.md §5 embeddings module.

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...


__all__ = [
    "EmbedderProtocol",
]