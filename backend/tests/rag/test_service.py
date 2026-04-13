"""Tests for the rag service."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import RagCompletedEvent
from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryQueryEmbedder,
)
from rag.models import ContextRecord, GraphContext, RetrievedContextItem
from rag.service import create_rag_service
from rag.service_models import RagQueryRequest


class RecordingGraphContextExpander:
    def __init__(self) -> None:
        self.calls = 0

    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext:
        self.calls += 1
        return GraphContext(summary=f"Graph context for {knowledge_base_id} with {len(context_items)} items")


def test_rag_service_answers_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    records = [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="Claim 42 was denied after a duplicate billing review.",
            metadata={"category": "claims"},
        )
    ]
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(records),
        InMemoryAnswerGenerator(),
        event_bus=event_bus,
        graph_context_expander=RecordingGraphContextExpander(),
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why was claim 42 denied?",
            top_k=1,
            filters={"category": "claims"},
        )
    )

    assert response.knowledge_base_id == "kb-1"
    assert len(response.citations) == 1
    assert response.graph_summary is not None
    assert isinstance(event_bus.published_events[-1], RagCompletedEvent)


def test_rag_service_skips_graph_expansion_when_disabled() -> None:
    event_bus = InMemoryEventBus()
    expander = RecordingGraphContextExpander()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(),
        InMemoryAnswerGenerator(),
        event_bus=event_bus,
        graph_context_expander=expander,
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Summarize provider risk",
            include_graph_context=False,
        )
    )

    assert response.graph_summary is None
    assert expander.calls == 0