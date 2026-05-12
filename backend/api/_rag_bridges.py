"""API composition adapters that bridge RAG ports to sibling services.

These adapters intentionally live in the API layer because they compose
multiple backend feature modules for frontend-initiated RAG requests. Keeping
them out of ``rag/`` preserves the backend hard rule that feature modules do
not directly import sibling feature modules.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from embeddings.protocols import EmbeddingsServiceProtocol
from embeddings.service_models import EmbeddedItem, EmbedRequest, EmbedSubmission
from graph.models import SubgraphResult
from llm.models import MessageRole
from llm.protocols import LlmServiceProtocol
from llm.service_models import ChatMessageInput, GenerateRequest
from rag.exceptions import RagConfigurationError
from rag.models import (
    GraphContext,
    GraphContextEdge,
    GraphContextNode,
    MetadataValue,
    RagGenerationRequest,
    RagGenerationResult,
    RetrievedContextItem,
)
from vectorstore.protocols import VectorServiceProtocol
from vectorstore.service_models import VectorSearchRequest


_DEFAULT_SYSTEM_PROMPT = (
    "You are a retrieval-augmented assistant. Use the provided context items "
    "to answer the user's question. If the context is insufficient, say so."
)
_CHAR_PER_TOKEN = 4
_BUDGET_FRACTION = 0.8
_MIN_TRUNCATED_CONTENT_CHARS = 16
_ENTITY_ID_KEYS: tuple[str, ...] = ("entity_id", "entityId", "entity")


class GraphNeighborhoodServiceProtocol(Protocol):
    """Narrow graph dependency required by the RAG graph bridge."""

    def query_neighborhood(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
    ) -> SubgraphResult: ...


class ServiceQueryEmbedder:
    """Adapter that satisfies RAG query embedding via the embeddings service."""

    def __init__(
        self,
        service: EmbeddingsServiceProtocol,
        *,
        model_name: str | None = None,
        content_id: str = "rag-query",
    ) -> None:
        self._service = service
        self._model_name = model_name
        self._content_id = content_id

    def embed_query(self, *, knowledge_base_id: str, question: str) -> list[float]:
        if question.strip() == "":
            raise RagConfigurationError("Query embedding requires a non-empty question.")

        submission = EmbedSubmission(content_id=self._content_id, content=question)
        request_kwargs: dict[str, object] = {
            "knowledge_base_id": knowledge_base_id,
            "submissions": [submission],
        }
        if self._model_name is not None:
            request_kwargs["model_name"] = self._model_name

        request = EmbedRequest.model_validate(request_kwargs)
        response = self._service.embed(request)

        items: list[EmbeddedItem] = list(response.items)
        if not items:
            raise RagConfigurationError(
                "Embeddings service returned no items for the query embedding request."
            )

        vector = list(items[0].vector)
        if not vector:
            raise RagConfigurationError(
                "Embeddings service returned an empty vector for the query embedding request."
            )
        return vector


class ServiceContextRetriever:
    """Adapter that satisfies RAG retrieval via the vectorstore service."""

    def __init__(self, service: VectorServiceProtocol) -> None:
        self._service = service

    def retrieve(
        self,
        *,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, str | int | float | bool],
    ) -> list[RetrievedContextItem]:
        request = VectorSearchRequest(
            knowledge_base_id=knowledge_base_id,
            query_vector=list(query_vector),
            limit=limit,
            filters=dict(filters),
        )
        response = self._service.search(request)

        items: list[RetrievedContextItem] = []
        for match in response.matches:
            metadata: dict[str, MetadataValue] = dict(match.metadata)
            content = match.content if match.content is not None else ""
            items.append(
                RetrievedContextItem(
                    record_id=match.record_id,
                    content_id=match.content_id,
                    score=match.score,
                    content=content,
                    metadata=metadata,
                )
            )
        return items


class ServiceGraphContextExpander:
    """Expand retrieved context via the graph service."""

    def __init__(
        self,
        graph_service: GraphNeighborhoodServiceProtocol,
        *,
        depth: int = 1,
    ) -> None:
        if depth < 0:
            raise ValueError("ServiceGraphContextExpander depth must be non-negative.")
        self._graph_service = graph_service
        self._depth = depth

    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext:
        seen_entity_ids: set[str] = set()
        ordered_entity_ids: list[str] = []
        for item in context_items:
            entity_id = _extract_entity_id(item)
            if entity_id is None or entity_id in seen_entity_ids:
                continue
            seen_entity_ids.add(entity_id)
            ordered_entity_ids.append(entity_id)

        nodes: list[GraphContextNode] = []
        edges: list[GraphContextEdge] = []
        seen_node_ids: set[str] = set()
        seen_edge_ids: set[str] = set()

        for entity_id in ordered_entity_ids:
            subgraph = self._graph_service.query_neighborhood(
                knowledge_base_id,
                entity_id,
                self._depth,
            )
            for entity in subgraph.entities:
                if entity.id in seen_node_ids:
                    continue
                seen_node_ids.add(entity.id)
                nodes.append(
                    GraphContextNode(
                        entity_id=entity.id,
                        entity_type=entity.type,
                        summary=_node_summary(entity.id, entity.type),
                    )
                )
            for relationship in subgraph.relationships:
                if relationship.id in seen_edge_ids:
                    continue
                seen_edge_ids.add(relationship.id)
                edges.append(
                    GraphContextEdge(
                        relationship_id=relationship.id,
                        relationship_type=relationship.type,
                        source_id=relationship.source_id,
                        target_id=relationship.target_id,
                        summary=None,
                    )
                )

        summary = _summary_for(nodes, edges)
        return GraphContext(nodes=nodes, edges=edges, summary=summary)


class ServiceAnswerGenerator:
    """Generate RAG answers by delegating to an LLM service implementation."""

    def __init__(
        self,
        llm_service: LlmServiceProtocol,
        *,
        max_tokens: int,
        model_name: str,
        temperature: float = 0.2,
        knowledge_base_id_in_request: bool = True,
    ) -> None:
        if max_tokens <= 0:
            raise ValueError("ServiceAnswerGenerator max_tokens must be positive.")
        if not model_name.strip():
            raise ValueError("ServiceAnswerGenerator model_name must not be empty.")
        if not 0.0 <= temperature <= 2.0:
            raise ValueError(
                "ServiceAnswerGenerator temperature must be between 0.0 and 2.0."
            )
        self._llm_service = llm_service
        self._max_tokens = max_tokens
        self._model_name = model_name
        self._temperature = temperature
        self._propagate_kb_id = knowledge_base_id_in_request

    def generate(self, request: RagGenerationRequest) -> RagGenerationResult:
        system_prompt = (request.system_prompt or _DEFAULT_SYSTEM_PROMPT).strip()
        budget_chars = int(self._max_tokens * _BUDGET_FRACTION) * _CHAR_PER_TOKEN
        fitted_items = _fit_context_to_budget(
            request.context_items,
            system_prompt=system_prompt,
            question=request.question,
            graph_summary=_graph_summary(request),
            budget_chars=budget_chars,
        )

        prompt = _assemble_prompt(
            system_prompt=system_prompt,
            context_items=fitted_items,
            graph_summary=_graph_summary(request),
            question=request.question,
        )

        generate_request = GenerateRequest(
            knowledge_base_id=request.knowledge_base_id if self._propagate_kb_id else None,
            model_name=self._model_name,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            messages=[
                ChatMessageInput(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessageInput(role=MessageRole.USER, content=prompt),
            ],
        )

        response = self._llm_service.generate(generate_request)
        return RagGenerationResult(
            request_id=request.request_id,
            answer=response.completion,
            provider=response.provider,
            model_name=response.model_name,
        )

    def stream_generate(self, request: RagGenerationRequest) -> Iterator[str]:
        result = self.generate(request)
        yield result.answer


def _extract_entity_id(item: RetrievedContextItem) -> str | None:
    for key in _ENTITY_ID_KEYS:
        raw = item.metadata.get(key)
        if isinstance(raw, str) and raw.strip() != "":
            return raw
    return None


def _node_summary(entity_id: str, entity_type: str) -> str:
    return f"{entity_type}:{entity_id}"


def _summary_for(
    nodes: list[GraphContextNode],
    edges: list[GraphContextEdge],
) -> str:
    if not nodes and not edges:
        return ""
    return f"Expanded {len(nodes)} graph nodes and {len(edges)} relationships."


def _graph_summary(request: RagGenerationRequest) -> str | None:
    if request.graph_context is None:
        return None
    summary = request.graph_context.summary
    if summary is None or summary.strip() == "":
        return None
    return summary


def _assemble_prompt(
    *,
    system_prompt: str,
    context_items: list[RetrievedContextItem],
    graph_summary: str | None,
    question: str,
) -> str:
    sections: list[str] = []
    if context_items:
        rendered_items = "\n\n".join(
            f"[{index + 1}] (record={item.record_id}, score={item.score:.4f})\n{item.content}"
            for index, item in enumerate(context_items)
        )
        sections.append(f"Context:\n{rendered_items}")
    else:
        sections.append("Context: (no retrieved context available)")
    if graph_summary is not None:
        sections.append(f"Graph context: {graph_summary}")
    sections.append(f"Question: {question}")
    return "\n\n".join(sections)


def _fit_context_to_budget(
    context_items: list[RetrievedContextItem],
    *,
    system_prompt: str,
    question: str,
    graph_summary: str | None,
    budget_chars: int,
) -> list[RetrievedContextItem]:
    if budget_chars <= 0:
        return []

    overhead_chars = (
        len(system_prompt) + len(question) + (len(graph_summary) if graph_summary else 0)
    )
    available_for_context = max(budget_chars - overhead_chars, 0)
    if available_for_context == 0:
        return []

    sorted_items = sorted(
        enumerate(context_items),
        key=lambda pair: pair[1].score,
        reverse=True,
    )
    selected: list[tuple[int, RetrievedContextItem]] = []
    total = 0
    for original_index, item in sorted_items:
        item_cost = len(item.content)
        if total + item_cost <= available_for_context:
            selected.append((original_index, item))
            total += item_cost
            continue
        remaining = available_for_context - total
        if remaining >= _MIN_TRUNCATED_CONTENT_CHARS:
            truncated_content = item.content[:remaining].rstrip()
            if truncated_content:
                truncated = item.model_copy(update={"content": truncated_content})
                selected.append((original_index, truncated))
                total += len(truncated_content)
        break

    selected.sort(key=lambda pair: pair[0])
    return [item for _, item in selected]


__all__ = [
    "ServiceAnswerGenerator",
    "ServiceContextRetriever",
    "ServiceGraphContextExpander",
    "ServiceQueryEmbedder",
]