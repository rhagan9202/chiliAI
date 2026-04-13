"""Service-level protocols for the embeddings module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from embeddings.service_models import EmbedRequest, EmbedResponse


@runtime_checkable
class EmbeddingsServiceProtocol(Protocol):
    """Service boundary for embedding generation."""

    def embed(self, request: EmbedRequest) -> EmbedResponse: ...


__all__ = [
    "EmbeddingsServiceProtocol",
]