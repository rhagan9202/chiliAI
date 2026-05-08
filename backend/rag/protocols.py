"""Service-level protocols for the rag module."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from rag.service_models import (
    RagAnswer,
    RagQueryRequest,
    RagQueryResponse,
    RagStreamChunk,
)


@runtime_checkable
class RagServiceProtocol(Protocol):
    """Service boundary for retrieval-augmented answer generation."""

    def answer(self, request: RagQueryRequest) -> RagQueryResponse: ...

    def answer_question(
        self,
        *,
        knowledge_base_id: str,
        question: str,
    ) -> RagAnswer: ...

    def stream_answer(
        self,
        request: RagQueryRequest,
    ) -> Iterator[RagStreamChunk]: ...


__all__ = [
    "RagServiceProtocol",
]
