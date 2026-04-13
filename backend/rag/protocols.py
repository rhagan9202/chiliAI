"""Service-level protocols for the rag module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag.service_models import RagQueryRequest, RagQueryResponse


@runtime_checkable
class RagServiceProtocol(Protocol):
    """Service boundary for retrieval-augmented answer generation."""

    # TODO(production): Add streaming answer generation:
    # - stream_answer(request: RagQueryRequest) -> Iterator[RagStreamChunk]
    # Add request validation, batch answering, and metrics/observability.
    # See docs/architecture.md §8 for RAG Chat page requirements.

    def answer(self, request: RagQueryRequest) -> RagQueryResponse: ...


__all__ = [
    "RagServiceProtocol",
]