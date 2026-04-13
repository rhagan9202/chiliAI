"""Adapter-level protocols for rag orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag.models import GraphContext, RagGenerationRequest, RagGenerationResult, RetrievedContextItem


@runtime_checkable
class QueryEmbedderProtocol(Protocol):
    """Produce a query vector for downstream retrieval."""

    def embed_query(self, *, knowledge_base_id: str, question: str) -> list[float]: ...


@runtime_checkable
class ContextRetrieverProtocol(Protocol):
    """Retrieve relevant context items for a query vector."""

    def retrieve(
        self,
        *,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, str | int | float | bool],
    ) -> list[RetrievedContextItem]: ...


@runtime_checkable
class GraphContextExpanderProtocol(Protocol):
    """Expand retrieval matches into graph-oriented context."""

    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext: ...


@runtime_checkable
class AnswerGeneratorProtocol(Protocol):
    """Generate a final answer from normalized rag context."""

    def generate(self, request: RagGenerationRequest) -> RagGenerationResult: ...


__all__ = [
    "AnswerGeneratorProtocol",
    "ContextRetrieverProtocol",
    "GraphContextExpanderProtocol",
    "QueryEmbedderProtocol",
]