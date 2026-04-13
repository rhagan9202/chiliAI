"""Service-level protocols for the rag module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag.service_models import RagQueryRequest, RagQueryResponse


@runtime_checkable
class RagServiceProtocol(Protocol):
    """Service boundary for retrieval-augmented answer generation."""

    def answer(self, request: RagQueryRequest) -> RagQueryResponse: ...


__all__ = [
    "RagServiceProtocol",
]