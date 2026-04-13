"""Adapter-level protocols for embedding providers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from embeddings.models import EmbeddingRequest, EmbeddingResult


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Generate vectors from embedding requests."""

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...