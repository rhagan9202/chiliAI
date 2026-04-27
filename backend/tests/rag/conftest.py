"""Shared fixtures for rag module tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from events.adapters.in_memory import InMemoryEventBus
from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryQueryEmbedder,
)
from rag.models import (
    ContextRecord,
    GraphContext,
    RagGenerationRequest,
    RagGenerationResult,
    RetrievedContextItem,
)


__all__ = [
    "RecordingAnswerGenerator",
    "RecordingGraphContextExpander",
    "default_records",
    "in_memory_answer_generator",
    "in_memory_context_retriever",
    "in_memory_event_bus",
    "in_memory_query_embedder",
]


class RecordingAnswerGenerator:
    """Answer generator that captures incoming requests for assertions."""

    def __init__(self) -> None:
        self.requests: list[RagGenerationRequest] = []

    def generate(self, request: RagGenerationRequest) -> RagGenerationResult:
        self.requests.append(request)
        return RagGenerationResult(
            request_id=request.request_id,
            answer=f"Answer: {request.question}",
            provider="recording",
            model_name="recording-model",
        )

    def stream_generate(self, request: RagGenerationRequest) -> Iterator[str]:
        self.requests.append(request)
        yield f"Answer: {request.question}"


class RecordingGraphContextExpander:
    """Graph expander that records calls and returns canned context."""

    def __init__(self) -> None:
        self.calls = 0

    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext:
        self.calls += 1
        return GraphContext(
            summary=(
                f"Graph context for {knowledge_base_id} "
                f"with {len(context_items)} items"
            )
        )


@pytest.fixture
def default_records() -> list[ContextRecord]:
    return [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="Claim 42 was denied after a duplicate billing review.",
            metadata={"category": "claims"},
        )
    ]


@pytest.fixture
def in_memory_event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def in_memory_query_embedder() -> InMemoryQueryEmbedder:
    return InMemoryQueryEmbedder()


@pytest.fixture
def in_memory_context_retriever(
    default_records: list[ContextRecord],
) -> InMemoryContextRetriever:
    return InMemoryContextRetriever(default_records)


@pytest.fixture
def in_memory_answer_generator() -> InMemoryAnswerGenerator:
    return InMemoryAnswerGenerator()
