"""Tests for the in-memory rag adapters."""

from __future__ import annotations

import pytest

from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryGraphContextExpander,
    InMemoryQueryEmbedder,
    InMemoryRagService,
)
from rag.exceptions import RagConfigurationError
from rag.models import (
    ContextRecord,
    GraphContext,
    RagGenerationRequest,
    RetrievedContextItem,
)
from rag.service_models import RagQueryRequest


def test_in_memory_query_embedder_is_deterministic() -> None:
    embedder = InMemoryQueryEmbedder()

    left = embedder.embed_query(knowledge_base_id="kb-1", question="Claim 42")
    right = embedder.embed_query(knowledge_base_id="kb-1", question="Claim 42")

    assert left == right


def test_in_memory_context_retriever_returns_best_match_first() -> None:
    retriever = InMemoryContextRetriever(
        records=[
            ContextRecord(
                record_id="record-1",
                content_id="content-1",
                embedding=[8.0, 5.0, 3.0, 2.0],
                content="Claim 42 duplicate billing",
            ),
            ContextRecord(
                record_id="record-2",
                content_id="content-2",
                embedding=[30.0, 24.0, 0.0, 5.0],
                content="Unrelated provider enrollment guidance",
            ),
        ]
    )

    results = retriever.retrieve(
        knowledge_base_id="kb-1",
        query_vector=[8.0, 5.0, 3.0, 2.0],
        limit=2,
        filters={},
    )

    assert [item.record_id for item in results] == ["record-1", "record-2"]


def test_in_memory_answer_generator_stream_yields_full_answer_in_one_chunk() -> None:
    generator = InMemoryAnswerGenerator()

    request = RagGenerationRequest(
        request_id="req-1",
        knowledge_base_id="kb-1",
        question="Why was claim 42 denied?",
    )

    chunks = list(generator.stream_generate(request))

    assert len(chunks) == 1
    assert "claim 42" in chunks[0].lower()


def test_in_memory_rag_service_answer_question_returns_canned_payload() -> None:
    service = InMemoryRagService(
        known_knowledge_base_ids={"kb-1"},
        canned_answer="Hello world.",
        canned_sources=["doc-1"],
    )

    answer = service.answer_question(knowledge_base_id="kb-1", question="hi?")

    assert answer.content == "Hello world."
    assert answer.sources == ["doc-1"]


def test_in_memory_rag_service_answer_returns_canned_response() -> None:
    service = InMemoryRagService(
        known_knowledge_base_ids={"kb-1"},
        canned_answer="Hello world.",
    )

    response = service.answer(
        RagQueryRequest(knowledge_base_id="kb-1", question="hi?")
    )

    assert response.answer == "Hello world."
    assert response.knowledge_base_id == "kb-1"


def test_in_memory_rag_service_unknown_kb_raises() -> None:
    service = InMemoryRagService(known_knowledge_base_ids={"kb-1"})

    with pytest.raises(RagConfigurationError):
        service.answer_question(knowledge_base_id="kb-missing", question="hi?")


def test_in_memory_rag_service_stream_answer_yields_done_sentinel() -> None:
    service = InMemoryRagService(
        known_knowledge_base_ids={"kb-1"},
        canned_answer="alpha beta",
        canned_sources=["doc-1"],
    )

    chunks = list(
        service.stream_answer(
            RagQueryRequest(knowledge_base_id="kb-1", question="hi?")
        )
    )

    assert [chunk.chunk_text for chunk in chunks[:-1]] == ["alpha ", "beta"]
    final = chunks[-1]
    assert final.is_final is True
    assert [citation.record_id for citation in final.citations] == ["doc-1"]


def test_in_memory_rag_service_stream_answer_unknown_kb_raises() -> None:
    service = InMemoryRagService(known_knowledge_base_ids={"kb-1"})

    with pytest.raises(RagConfigurationError):
        list(
            service.stream_answer(
                RagQueryRequest(knowledge_base_id="kb-missing", question="hi?")
            )
        )


def test_in_memory_context_retriever_filters_records_with_metadata() -> None:
    retriever = InMemoryContextRetriever(
        records=[
            ContextRecord(
                record_id="claims-1",
                content_id="c-1",
                embedding=[8.0, 5.0, 3.0, 2.0],
                content="claim record",
                metadata={"category": "claims"},
            ),
            ContextRecord(
                record_id="enrollment-1",
                content_id="c-2",
                embedding=[8.0, 5.0, 3.0, 2.0],
                content="enrollment record",
                metadata={"category": "enrollment"},
            ),
        ]
    )

    results = retriever.retrieve(
        knowledge_base_id="kb-1",
        query_vector=[8.0, 5.0, 3.0, 2.0],
        limit=5,
        filters={"category": "claims"},
    )

    assert [item.record_id for item in results] == ["claims-1"]


def test_in_memory_context_retriever_zero_query_vector_yields_zero_score() -> None:
    retriever = InMemoryContextRetriever(
        records=[
            ContextRecord(
                record_id="r-1",
                content_id="c-1",
                embedding=[1.0, 0.0, 0.0, 0.0],
                content="text",
            )
        ]
    )

    results = retriever.retrieve(
        knowledge_base_id="kb-1",
        query_vector=[0.0, 0.0, 0.0, 0.0],
        limit=1,
        filters={},
    )

    assert results[0].score == 0.0


def test_in_memory_context_retriever_dimension_mismatch_raises_value_error() -> None:
    retriever = InMemoryContextRetriever(
        records=[
            ContextRecord(
                record_id="r-1",
                content_id="c-1",
                embedding=[1.0, 0.0, 0.0, 0.0],
                content="text",
            )
        ]
    )

    with pytest.raises(ValueError, match="dimensions must match"):
        retriever.retrieve(
            knowledge_base_id="kb-1",
            query_vector=[1.0, 2.0],
            limit=1,
            filters={},
        )


def test_in_memory_graph_expander_builds_nodes_and_edges() -> None:
    expander = InMemoryGraphContextExpander()

    items = [
        RetrievedContextItem(
            record_id=f"r-{i}",
            content_id=f"c-{i}",
            score=0.5,
            content="snippet",
            metadata={},
        )
        for i in range(3)
    ]

    context = expander.expand(knowledge_base_id="kb-1", context_items=items)

    assert isinstance(context, GraphContext)
    assert [node.entity_id for node in context.nodes] == [
        "kb-1:c-0",
        "kb-1:c-1",
        "kb-1:c-2",
    ]
    assert len(context.edges) == 2
    assert context.edges[0].source_id == "kb-1:c-0"
    assert context.edges[0].target_id == "kb-1:c-1"
    assert context.summary is not None
    assert "3 graph nodes" in context.summary


def test_in_memory_graph_expander_empty_items_returns_empty_summary() -> None:
    expander = InMemoryGraphContextExpander()

    context = expander.expand(knowledge_base_id="kb-1", context_items=[])

    assert context.nodes == []
    assert context.edges == []
    assert context.summary == "Expanded 0 graph nodes from retrieved evidence."


def test_in_memory_answer_generator_includes_graph_summary_in_answer() -> None:
    generator = InMemoryAnswerGenerator()

    request = RagGenerationRequest(
        request_id="req-1",
        knowledge_base_id="kb-1",
        question="Why?",
        graph_context=GraphContext(summary="2 nodes."),
    )

    result = generator.generate(request)

    assert "Graph: 2 nodes." in result.answer
