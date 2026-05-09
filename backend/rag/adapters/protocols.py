"""Adapter-level protocols for rag orchestration."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from rag.models import GraphContext, RagGenerationRequest, RagGenerationResult, RetrievedContextItem


@runtime_checkable
class QueryEmbedderProtocol(Protocol):
    """Produce a query vector for downstream retrieval."""

    def embed_query(self, *, knowledge_base_id: str, question: str) -> list[float]: ...


@runtime_checkable
class ContextRetrieverProtocol(Protocol):
    """Retrieve relevant context items for a query vector."""

    # TODO(production): Add min_score threshold, cursor-based pagination, and
    # hybrid search (keyword + semantic). Add reranking stage parameter.
    # Add timeout_ms for retrieval deadline enforcement.

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

    # TODO(production): Add configurable expansion depth, entity type filters,
    # and timeout parameters. Implement Neo4j-backed expander adapter.

    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext: ...


@runtime_checkable
class AnswerGeneratorProtocol(Protocol):
    """Generate a final answer from normalized rag context."""

    # TODO(production): Add token budget awareness and citation formatting
    # options. Implement production adapters: OpenAI, Anthropic, LangChain.

    def generate(self, request: RagGenerationRequest) -> RagGenerationResult: ...

    def stream_generate(self, request: RagGenerationRequest) -> Iterator[str]: ...


__all__ = [
    "AnswerGeneratorProtocol",
    "ContextRetrieverProtocol",
    "GraphContextExpanderProtocol",
    "QueryEmbedderProtocol",
]
