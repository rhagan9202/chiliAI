"""Tests for the rag service."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from config.schema import (
    AlertsConfig,
    CapabilitiesConfig,
    ChunkingConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    IngestionSourceConfig,
    RagConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import RagCompletedEvent
from rag.adapters.in_memory import (
    InMemoryAnswerGenerator,
    InMemoryContextRetriever,
    InMemoryQueryEmbedder,
)
from rag.exceptions import (
    RagConfigurationError,
    RagGenerationError,
    RagRetrievalError,
)
from rag.models import (
    ContextRecord,
    GraphContext,
    RagGenerationRequest,
    RagGenerationResult,
    RetrievedContextItem,
)
from rag.service import RagService, create_rag_service
from rag.service_models import RagCitation, RagQueryRequest, RagStreamChunk
from shared.types import EntityDefinition, PropertyDefinition, PropertyType


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


class FailingAnswerGenerator:
    def generate(self, request: RagGenerationRequest) -> RagGenerationResult:
        raise RuntimeError("boom")

    def stream_generate(self, request: RagGenerationRequest) -> Iterator[str]:
        del request
        raise RuntimeError("boom")
        yield ""  # pragma: no cover - unreachable, makes function a generator


class FailingContextRetriever:
    def retrieve(
        self,
        *,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, str | int | float | bool],
    ) -> list[RetrievedContextItem]:
        del knowledge_base_id, query_vector, limit, filters
        raise RuntimeError("retrieval-boom")


def _entity(name: str, label: str) -> EntityDefinition:
    return EntityDefinition(
        name=name,
        display_label=label,
        icon="box",
        properties={"id": PropertyDefinition(type=PropertyType.STRING, display="ID")},
    )


def _domain_config(
    *,
    template: str | None = None,
    entities: list[EntityDefinition] | None = None,
    display_name: str = "Test Domain",
) -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name=display_name, description="d"),
        entities=entities
        or [_entity("provider", "Provider"), _entity("claim", "Claim")],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(
            sources=[IngestionSourceConfig(type="file_upload", formats=["pdf"])],
            chunking=ChunkingConfig(),
        ),
        rag=RagConfig(system_prompt_template=template),
        alerts=AlertsConfig(thresholds={"provider": {"risk_score": 0.5}}),
    )


def _records() -> list[ContextRecord]:
    return [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="Claim 42 was denied after a duplicate billing review.",
            metadata={"category": "claims"},
        )
    ]


def test_rag_service_answers_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
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


def test_rag_service_answer_question_returns_simplified_answer() -> None:
    event_bus = InMemoryEventBus()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        InMemoryAnswerGenerator(),
        event_bus=event_bus,
    )

    answer = service.answer_question(
        knowledge_base_id="kb-1",
        question="Why was claim 42 denied?",
    )

    assert "claim 42" in answer.content.lower()
    assert answer.sources == ["record-1"]


def test_rag_service_retrieval_failure_raises_rag_retrieval_error() -> None:
    event_bus = InMemoryEventBus()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        FailingContextRetriever(),
        InMemoryAnswerGenerator(),
        event_bus=event_bus,
    )

    with pytest.raises(RagRetrievalError):
        service.answer(
            RagQueryRequest(knowledge_base_id="kb-1", question="anything?")
        )


def test_rag_service_generation_failure_raises_rag_generation_error() -> None:
    event_bus = InMemoryEventBus()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        FailingAnswerGenerator(),
        event_bus=event_bus,
    )

    with pytest.raises(RagGenerationError):
        service.answer(
            RagQueryRequest(knowledge_base_id="kb-1", question="anything?")
        )


# ---------------------------------------------------------------------------
# E6-S05: Domain-configurable system prompt
# ---------------------------------------------------------------------------


def test_request_system_prompt_overrides_domain_template() -> None:
    generator = RecordingAnswerGenerator()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        generator,
        event_bus=InMemoryEventBus(),
        domain_config=_domain_config(template="domain-level prompt for {domain_name}"),
    )

    service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
            system_prompt="caller-supplied prompt",
        )
    )

    assert generator.requests[-1].system_prompt == "caller-supplied prompt"


def test_falls_back_to_domain_template_when_request_omits_prompt() -> None:
    generator = RecordingAnswerGenerator()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        generator,
        event_bus=InMemoryEventBus(),
        domain_config=_domain_config(
            template="Helping with {domain_name}; entities: {entity_types}.",
            display_name="Medicare Fraud",
            entities=[_entity("provider", "Provider"), _entity("claim", "Claim")],
        ),
    )

    service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )

    assert (
        generator.requests[-1].system_prompt
        == "Helping with Medicare Fraud; entities: Provider, Claim."
    )


def test_unknown_placeholder_in_template_is_preserved() -> None:
    generator = RecordingAnswerGenerator()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        generator,
        event_bus=InMemoryEventBus(),
        domain_config=_domain_config(template="Hello {domain_name} {unknown}"),
    )

    service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )

    rendered = generator.requests[-1].system_prompt
    assert rendered is not None
    assert "Test Domain" in rendered
    assert "{unknown}" in rendered


def test_system_prompt_is_none_when_no_domain_config_provided() -> None:
    generator = RecordingAnswerGenerator()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        generator,
        event_bus=InMemoryEventBus(),
    )

    service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )

    assert generator.requests[-1].system_prompt is None


# ---------------------------------------------------------------------------
# E6-S06: Streaming RAG
# ---------------------------------------------------------------------------


def test_stream_answer_yields_final_chunk_with_citations() -> None:
    event_bus = InMemoryEventBus()
    service: RagService = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        InMemoryAnswerGenerator(),
        event_bus=event_bus,
    )

    chunks = list(
        service.stream_answer(
            RagQueryRequest(
                knowledge_base_id="kb-1",
                question="Why was claim 42 denied?",
                include_graph_context=False,
            )
        )
    )

    assert len(chunks) >= 2
    body = "".join(chunk.chunk_text for chunk in chunks if not chunk.is_final)
    assert "claim 42" in body.lower()

    final = chunks[-1]
    assert final.is_final is True
    assert final.chunk_text == ""
    assert len(final.citations) == 1
    assert final.citations[0].record_id == "record-1"

    for chunk in chunks[:-1]:
        assert chunk.is_final is False
        assert chunk.citations == []


def test_stream_answer_propagates_generation_failure() -> None:
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        FailingAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(RagGenerationError):
        list(
            service.stream_answer(
                RagQueryRequest(
                    knowledge_base_id="kb-1",
                    question="Why?",
                    include_graph_context=False,
                )
            )
        )


# ---------------------------------------------------------------------------
# E6-S07: Citation formatting and ordering
# ---------------------------------------------------------------------------


def test_citations_are_ordered_by_descending_score() -> None:
    records = [
        ContextRecord(
            record_id="low",
            content_id="content-low",
            embedding=[1.0, 0.0, 0.0, 1.0],
            content="Low signal text.",
        ),
        ContextRecord(
            record_id="high",
            content_id="content-high",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="High signal text mentioning claim 42.",
        ),
    ]
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(records),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="claim 42",
            top_k=2,
            include_graph_context=False,
        )
    )

    scores = [citation.score for citation in response.citations]
    assert scores == sorted(scores, reverse=True)


def test_citation_metadata_is_mapped_when_present() -> None:
    records = [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="Highlighted source text.",
            metadata={
                "document_id": "doc-42",
                "chunk_index": 7,
                "highlight": "Highlighted span.",
            },
        )
    ]
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(records),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="anything",
            include_graph_context=False,
        )
    )

    citation = response.citations[0]
    assert citation.document_id == "doc-42"
    assert citation.chunk_index == 7
    assert citation.highlight == "Highlighted span."


def test_citation_falls_back_to_text_metadata_for_highlight() -> None:
    records = [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="Body text.",
            metadata={"text": "fallback span"},
        )
    ]
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(records),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="anything",
            include_graph_context=False,
        )
    )

    citation = response.citations[0]
    assert citation.highlight == "fallback span"


def test_citation_metadata_missing_results_in_none_fields() -> None:
    records = [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="Body without metadata.",
        )
    ]
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(records),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="anything",
            include_graph_context=False,
        )
    )

    citation = response.citations[0]
    assert citation.document_id is None
    assert citation.chunk_index is None
    assert citation.highlight is None


def test_citation_ignores_non_matching_metadata_types() -> None:
    records = [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content="Body.",
            metadata={"document_id": 123, "chunk_index": True},
        )
    ]
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(records),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="anything",
            include_graph_context=False,
        )
    )

    citation = response.citations[0]
    assert citation.document_id is None
    assert citation.chunk_index is None


def test_citation_keeps_explicit_records_for_assertion() -> None:
    """Ensure ``RagCitation`` is exported and constructible from the rag module."""

    citation = RagCitation(
        record_id="r",
        content_id="c",
        score=0.5,
        snippet="snippet",
        document_id="doc-1",
        chunk_index=2,
        highlight="hi",
    )
    chunk = RagStreamChunk(chunk_text="", is_final=True, citations=[citation])
    assert chunk.citations[0].document_id == "doc-1"


# ---------------------------------------------------------------------------
# E6-S08: Coverage gate for AC scenarios (config errors, empty context,
# graph-expansion failure, streaming partial failure).
# ---------------------------------------------------------------------------


class _ValueErrorEmbedder:
    def embed_query(self, *, knowledge_base_id: str, question: str) -> list[float]:
        del knowledge_base_id, question
        raise ValueError("invalid embedding configuration")


class _ValueErrorRetriever:
    def retrieve(
        self,
        *,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, str | int | float | bool],
    ) -> list[RetrievedContextItem]:
        del knowledge_base_id, query_vector, limit, filters
        raise ValueError("retrieval configuration error")


class _ValueErrorAnswerGenerator:
    def generate(self, request: RagGenerationRequest) -> RagGenerationResult:
        del request
        raise ValueError("generator configuration error")

    def stream_generate(self, request: RagGenerationRequest) -> Iterator[str]:
        del request
        raise ValueError("generator configuration error")
        yield ""  # pragma: no cover - generator marker


class _ValueErrorGraphExpander:
    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext:
        del knowledge_base_id, context_items
        raise ValueError("graph expander configuration error")


class _FailingGraphExpander:
    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext:
        del knowledge_base_id, context_items
        raise RuntimeError("graph-boom")


class _PartialStreamAnswerGenerator:
    """Yields a valid first chunk before raising mid-stream."""

    def generate(self, request: RagGenerationRequest) -> RagGenerationResult:
        return RagGenerationResult(
            request_id=request.request_id,
            answer="unused",
            provider="partial",
            model_name="partial-model",
        )

    def stream_generate(self, request: RagGenerationRequest) -> Iterator[str]:
        del request
        yield "partial chunk "
        raise RuntimeError("stream-boom")


class _EmptyContextRetriever:
    def retrieve(
        self,
        *,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, str | int | float | bool],
    ) -> list[RetrievedContextItem]:
        del knowledge_base_id, query_vector, limit, filters
        return []


def test_answer_value_error_in_embedder_raises_rag_configuration_error() -> None:
    service = create_rag_service(
        _ValueErrorEmbedder(),
        InMemoryContextRetriever(_records()),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(RagConfigurationError, match="invalid embedding"):
        service.answer(RagQueryRequest(knowledge_base_id="kb-1", question="q?"))


def test_answer_value_error_in_retriever_raises_rag_configuration_error() -> None:
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        _ValueErrorRetriever(),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(RagConfigurationError, match="retrieval configuration"):
        service.answer(RagQueryRequest(knowledge_base_id="kb-1", question="q?"))


def test_answer_value_error_in_generator_raises_rag_configuration_error() -> None:
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        _ValueErrorAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(RagConfigurationError, match="generator configuration"):
        service.answer(RagQueryRequest(knowledge_base_id="kb-1", question="q?"))


def test_answer_with_empty_context_still_returns_response_without_citations() -> None:
    event_bus = InMemoryEventBus()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        _EmptyContextRetriever(),
        InMemoryAnswerGenerator(),
        event_bus=event_bus,
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )

    assert response.citations == []
    assert response.graph_summary is None
    completed = event_bus.published_events[-1]
    assert isinstance(completed, RagCompletedEvent)
    assert completed.replies[0].context_item_count == 0
    assert completed.replies[0].citation_count == 0


def test_graph_expansion_runtime_failure_raises_rag_retrieval_error() -> None:
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
        graph_context_expander=_FailingGraphExpander(),
    )

    with pytest.raises(RagRetrievalError, match="expand graph context"):
        service.answer(
            RagQueryRequest(
                knowledge_base_id="kb-1",
                question="Why?",
                include_graph_context=True,
            )
        )


def test_graph_expansion_value_error_raises_rag_configuration_error() -> None:
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
        graph_context_expander=_ValueErrorGraphExpander(),
    )

    with pytest.raises(RagConfigurationError, match="graph expander configuration"):
        service.answer(
            RagQueryRequest(
                knowledge_base_id="kb-1",
                question="Why?",
                include_graph_context=True,
            )
        )


def test_stream_answer_value_error_in_generator_raises_rag_configuration_error() -> None:
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        _ValueErrorAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(RagConfigurationError, match="generator configuration"):
        list(
            service.stream_answer(
                RagQueryRequest(
                    knowledge_base_id="kb-1",
                    question="q?",
                    include_graph_context=False,
                )
            )
        )


def test_stream_answer_partial_failure_yields_then_raises() -> None:
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        _PartialStreamAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    iterator = service.stream_answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )
    first = next(iterator)
    assert first.is_final is False
    assert first.chunk_text == "partial chunk "

    with pytest.raises(RagGenerationError, match="generate rag answer"):
        next(iterator)


def test_domain_config_with_no_rag_section_yields_no_system_prompt() -> None:
    generator = RecordingAnswerGenerator()
    config = _domain_config(template=None)
    config_no_rag = config.model_copy(update={"rag": None})

    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        generator,
        event_bus=InMemoryEventBus(),
        domain_config=config_no_rag,
    )

    service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )

    assert generator.requests[-1].system_prompt is None


def test_domain_config_with_rag_but_no_template_yields_no_system_prompt() -> None:
    generator = RecordingAnswerGenerator()
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        generator,
        event_bus=InMemoryEventBus(),
        domain_config=_domain_config(template=None),
    )

    service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )

    assert generator.requests[-1].system_prompt is None


def test_malformed_template_falls_back_to_raw_text() -> None:
    generator = RecordingAnswerGenerator()
    # Use an unmatched single brace and a positional reference (e.g. {0})
    # which raises IndexError under format_map and triggers the fallback.
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(_records()),
        generator,
        event_bus=InMemoryEventBus(),
        domain_config=_domain_config(template="prefix {0} suffix"),
    )

    service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="Why?",
            include_graph_context=False,
        )
    )

    assert generator.requests[-1].system_prompt == "prefix {0} suffix"


def test_long_content_snippet_is_truncated_with_ellipsis() -> None:
    long_content = "alpha " * 100  # well over the 160-char snippet limit
    records = [
        ContextRecord(
            record_id="record-1",
            content_id="content-1",
            embedding=[20.0, 16.0, 3.0, 4.0],
            content=long_content,
        )
    ]
    service = create_rag_service(
        InMemoryQueryEmbedder(),
        InMemoryContextRetriever(records),
        InMemoryAnswerGenerator(),
        event_bus=InMemoryEventBus(),
    )

    response = service.answer(
        RagQueryRequest(
            knowledge_base_id="kb-1",
            question="anything",
            include_graph_context=False,
        )
    )

    snippet = response.citations[0].snippet
    assert snippet.endswith("...")
    assert len(snippet) <= 160
