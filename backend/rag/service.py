"""Service entry point for retrieval-augmented generation flows."""

from __future__ import annotations

from collections.abc import Iterator

from config.schema import DomainConfig
from events.protocols import EventBus
from events.types import RagCompletedEvent, RagCompletionReference
from rag.adapters.protocols import (
    AnswerGeneratorProtocol,
    ContextRetrieverProtocol,
    GraphContextExpanderProtocol,
    QueryEmbedderProtocol,
)
from rag.exceptions import RagConfigurationError, RagGenerationError, RagRetrievalError
from rag.models import (
    GraphContext,
    MetadataValue,
    RagGenerationRequest,
    RagWorkflowState,
    RetrievedContextItem,
)
from rag.service_models import (
    RagAnswer,
    RagCitation,
    RagQueryRequest,
    RagQueryResponse,
    RagStreamChunk,
)
from shared.utils import generate_id


_DEFAULT_SYSTEM_PROMPT = (
    "You are a retrieval-augmented assistant. Use the provided context items "
    "to answer the user's question. If the context is insufficient, say so."
)


class RagService:
    """Coordinate query embedding, retrieval, context assembly, and answer generation."""

    # TODO(production): Add retry logic with backoff on retrieval/generation failures.
    # Add timeout enforcement per pipeline stage. Add request caching/memoization
    # for repeated questions. Add graceful degradation: if graph expansion fails,
    # continue with basic context rather than propagating the error. Add circuit
    # breaker for flaky LLM providers.

    def __init__(
        self,
        query_embedder: QueryEmbedderProtocol,
        context_retriever: ContextRetrieverProtocol,
        answer_generator: AnswerGeneratorProtocol,
        *,
        event_bus: EventBus,
        graph_context_expander: GraphContextExpanderProtocol | None = None,
        domain_config: DomainConfig | None = None,
    ) -> None:
        self._query_embedder = query_embedder
        self._context_retriever = context_retriever
        self._answer_generator = answer_generator
        self._event_bus = event_bus
        self._graph_context_expander = graph_context_expander
        self._domain_config = domain_config

    def answer(self, request: RagQueryRequest) -> RagQueryResponse:
        state = self._prepare_state(request)
        graph_context = self._expand_graph_context(state, request)
        generation_request = self._build_generation_request(state, request, graph_context)

        try:
            generation_result = self._answer_generator.generate(generation_request)
        except ValueError as exc:
            raise RagConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RagGenerationError("Failed to generate rag answer.") from exc

        citations = _build_citations(state.context_items)
        response = RagQueryResponse(
            request_id=generation_result.request_id,
            knowledge_base_id=state.knowledge_base_id,
            answer=generation_result.answer,
            provider=generation_result.provider,
            model_name=generation_result.model_name,
            citations=citations,
            graph_summary=graph_context.summary if graph_context is not None else None,
        )
        self._publish_completed_event(response, len(state.context_items))
        return response

    def answer_question(
        self,
        *,
        knowledge_base_id: str,
        question: str,
    ) -> RagAnswer:
        response = self.answer(
            RagQueryRequest(
                knowledge_base_id=knowledge_base_id,
                question=question,
                include_graph_context=False,
            )
        )
        return RagAnswer(
            content=response.answer,
            sources=[citation.record_id for citation in response.citations],
        )

    def stream_answer(self, request: RagQueryRequest) -> Iterator[RagStreamChunk]:
        state = self._prepare_state(request)
        graph_context = self._expand_graph_context(state, request)
        generation_request = self._build_generation_request(state, request, graph_context)

        try:
            stream = self._answer_generator.stream_generate(generation_request)
            for chunk_text in stream:
                yield RagStreamChunk(chunk_text=chunk_text, is_final=False)
        except ValueError as exc:
            raise RagConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RagGenerationError("Failed to generate rag answer.") from exc

        yield RagStreamChunk(
            chunk_text="",
            is_final=True,
            citations=_build_citations(state.context_items),
        )

    def _prepare_state(self, request: RagQueryRequest) -> RagWorkflowState:
        state = RagWorkflowState(
            request_id=generate_id(),
            knowledge_base_id=request.knowledge_base_id,
            question=request.question,
        )
        try:
            query_vector = self._query_embedder.embed_query(
                knowledge_base_id=state.knowledge_base_id,
                question=state.question,
            )
            state = state.model_copy(update={"query_vector": query_vector})
            context_items = self._context_retriever.retrieve(
                knowledge_base_id=state.knowledge_base_id,
                query_vector=query_vector,
                limit=request.top_k,
                filters=_string_filters(request.filters),
            )
        except ValueError as exc:
            raise RagConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RagRetrievalError("Failed to retrieve rag context.") from exc

        return state.model_copy(update={"context_items": context_items})

    def _build_generation_request(
        self,
        state: RagWorkflowState,
        request: RagQueryRequest,
        graph_context: GraphContext | None,
    ) -> RagGenerationRequest:
        system_prompt = self._resolve_system_prompt(request)
        return RagGenerationRequest(
            request_id=state.request_id,
            knowledge_base_id=state.knowledge_base_id,
            question=state.question,
            context_items=state.context_items,
            graph_context=graph_context,
            system_prompt=system_prompt,
        )

    def _resolve_system_prompt(self, request: RagQueryRequest) -> str | None:
        if request.system_prompt is not None:
            return request.system_prompt

        domain_config = self._domain_config
        if domain_config is None or domain_config.rag is None:
            return None

        template_text = domain_config.rag.system_prompt_template
        if template_text is None:
            return None

        return _render_system_prompt(template_text, domain_config)

    def _expand_graph_context(
        self,
        state: RagWorkflowState,
        request: RagQueryRequest,
    ) -> GraphContext | None:
        if not request.include_graph_context or self._graph_context_expander is None:
            return None
        try:
            return self._graph_context_expander.expand(
                knowledge_base_id=state.knowledge_base_id,
                context_items=state.context_items,
            )
        except ValueError as exc:
            raise RagConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RagRetrievalError("Failed to expand graph context.") from exc

    def _publish_completed_event(
        self,
        response: RagQueryResponse,
        context_item_count: int,
    ) -> None:
        self._event_bus.publish(
            RagCompletedEvent(
                replies=[
                    RagCompletionReference(
                        knowledge_base_id=response.knowledge_base_id,
                        request_id=response.request_id,
                        provider=response.provider,
                        model_name=response.model_name,
                        context_item_count=context_item_count,
                        citation_count=len(response.citations),
                        answer_length=len(response.answer),
                    )
                ]
            )
        )


def create_rag_service(
    query_embedder: QueryEmbedderProtocol,
    context_retriever: ContextRetrieverProtocol,
    answer_generator: AnswerGeneratorProtocol,
    *,
    event_bus: EventBus,
    graph_context_expander: GraphContextExpanderProtocol | None = None,
    domain_config: DomainConfig | None = None,
) -> RagService:
    """Create the default rag service."""

    return RagService(
        query_embedder,
        context_retriever,
        answer_generator,
        event_bus=event_bus,
        graph_context_expander=graph_context_expander,
        domain_config=domain_config,
    )


def _build_citations(context_items: list[RetrievedContextItem]) -> list[RagCitation]:
    indexed = list(enumerate(context_items))
    indexed.sort(key=lambda pair: (-pair[1].score, pair[0]))
    return [_citation_for(item) for _, item in indexed]


def _citation_for(item: RetrievedContextItem) -> RagCitation:
    metadata = item.metadata
    document_id = _string_field(metadata.get("document_id"))
    chunk_index = _int_field(metadata.get("chunk_index"))
    highlight = _string_field(metadata.get("highlight"))
    if highlight is None:
        highlight = _string_field(metadata.get("text"))
    return RagCitation(
        record_id=item.record_id,
        content_id=item.content_id,
        score=item.score,
        snippet=_snippet(item.content),
        document_id=document_id,
        chunk_index=chunk_index,
        highlight=highlight,
    )


def _string_field(value: MetadataValue | None) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _int_field(value: MetadataValue | None) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _string_filters(
    filters: dict[str, MetadataValue],
) -> dict[str, str | int | float | bool]:
    return dict(filters)


class _SafeFormatMap(dict[str, str]):
    """Mapping that returns ``{key}`` for unknown placeholders.

    Used with ``str.format_map`` so unknown ``{...}`` tokens are preserved
    rather than raising ``KeyError``.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_system_prompt(template_text: str, domain_config: DomainConfig) -> str:
    entity_types = ", ".join(entity.display_label for entity in domain_config.entities)
    mapping = _SafeFormatMap(
        domain_name=domain_config.domain.display_name,
        entity_types=entity_types,
    )
    try:
        return template_text.format_map(mapping)
    except (IndexError, ValueError):
        # Malformed template: fall back to the raw text rather than crashing.
        return template_text


def _snippet(content: str, *, limit: int = 160) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


__all__ = ["RagService", "create_rag_service"]
