"""Service entry point for retrieval-augmented generation flows."""

from __future__ import annotations

from events.protocols import EventBus
from events.types import RagCompletedEvent, RagCompletionReference
from rag.adapters.protocols import (
    AnswerGeneratorProtocol,
    ContextRetrieverProtocol,
    GraphContextExpanderProtocol,
    QueryEmbedderProtocol,
)
from rag.exceptions import RagConfigurationError, RagGenerationError, RagRetrievalError
from rag.models import GraphContext, RagGenerationRequest, RagWorkflowState
from rag.service_models import RagCitation, RagQueryRequest, RagQueryResponse
from shared.utils import generate_id


class RagService:
    """Coordinate query embedding, retrieval, context assembly, and answer generation."""

    def __init__(
        self,
        query_embedder: QueryEmbedderProtocol,
        context_retriever: ContextRetrieverProtocol,
        answer_generator: AnswerGeneratorProtocol,
        *,
        event_bus: EventBus,
        graph_context_expander: GraphContextExpanderProtocol | None = None,
    ) -> None:
        self._query_embedder = query_embedder
        self._context_retriever = context_retriever
        self._answer_generator = answer_generator
        self._event_bus = event_bus
        self._graph_context_expander = graph_context_expander

    def answer(self, request: RagQueryRequest) -> RagQueryResponse:
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
                filters=request.filters,
            )
        except ValueError as exc:
            raise RagConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RagRetrievalError("Failed to retrieve rag context.") from exc

        state = state.model_copy(update={"context_items": context_items})
        graph_context = self._expand_graph_context(state, request)

        generation_request = RagGenerationRequest(
            request_id=state.request_id,
            knowledge_base_id=state.knowledge_base_id,
            question=state.question,
            context_items=state.context_items,
            graph_context=graph_context,
            system_prompt=request.system_prompt,
        )

        try:
            generation_result = self._answer_generator.generate(generation_request)
        except ValueError as exc:
            raise RagConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise RagGenerationError("Failed to generate rag answer.") from exc

        response = RagQueryResponse(
            request_id=generation_result.request_id,
            knowledge_base_id=state.knowledge_base_id,
            answer=generation_result.answer,
            provider=generation_result.provider,
            model_name=generation_result.model_name,
            citations=[
                RagCitation(
                    record_id=item.record_id,
                    content_id=item.content_id,
                    score=item.score,
                    snippet=_snippet(item.content),
                )
                for item in state.context_items
            ],
            graph_summary=graph_context.summary if graph_context is not None else None,
        )
        self._event_bus.publish(
            RagCompletedEvent(
                replies=[
                    RagCompletionReference(
                        knowledge_base_id=response.knowledge_base_id,
                        request_id=response.request_id,
                        provider=response.provider,
                        model_name=response.model_name,
                        context_item_count=len(state.context_items),
                        citation_count=len(response.citations),
                        answer_length=len(response.answer),
                    )
                ]
            )
        )
        return response

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


def create_rag_service(
    query_embedder: QueryEmbedderProtocol,
    context_retriever: ContextRetrieverProtocol,
    answer_generator: AnswerGeneratorProtocol,
    *,
    event_bus: EventBus,
    graph_context_expander: GraphContextExpanderProtocol | None = None,
) -> RagService:
    """Create the default rag service."""

    return RagService(
        query_embedder,
        context_retriever,
        answer_generator,
        event_bus=event_bus,
        graph_context_expander=graph_context_expander,
    )


def _snippet(content: str, *, limit: int = 160) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


__all__ = ["RagService", "create_rag_service"]