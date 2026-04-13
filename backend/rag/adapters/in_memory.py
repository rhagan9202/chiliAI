"""In-memory rag adapters for tests and local development."""

from __future__ import annotations

from math import sqrt

from rag.models import (
    ContextRecord,
    GraphContext,
    GraphContextEdge,
    GraphContextNode,
    RagGenerationRequest,
    RagGenerationResult,
    RetrievedContextItem,
)


class InMemoryQueryEmbedder:
    """A deterministic embedder that encodes simple text statistics."""

    def embed_query(self, *, knowledge_base_id: str, question: str) -> list[float]:
        del knowledge_base_id
        return _embed_text(question)


class InMemoryContextRetriever:
    """A deterministic similarity retriever over seeded context records."""

    def __init__(self, records: list[ContextRecord] | None = None) -> None:
        self._records = list(records or [])

    def retrieve(
        self,
        *,
        knowledge_base_id: str,
        query_vector: list[float],
        limit: int,
        filters: dict[str, str | int | float | bool],
    ) -> list[RetrievedContextItem]:
        del knowledge_base_id
        scored_records: list[tuple[float, ContextRecord]] = []
        for record in self._records:
            if not _matches_filters(record, filters):
                continue
            scored_records.append((_cosine_similarity(query_vector, record.embedding), record))

        scored_records.sort(key=lambda item: item[0], reverse=True)
        return [
            RetrievedContextItem(
                record_id=record.record_id,
                content_id=record.content_id,
                score=score,
                content=record.content,
                metadata=dict(record.metadata),
            )
            for score, record in scored_records[:limit]
        ]


class InMemoryGraphContextExpander:
    """A graph-context expander that derives nodes from retrieved items."""

    def expand(
        self,
        *,
        knowledge_base_id: str,
        context_items: list[RetrievedContextItem],
    ) -> GraphContext:
        nodes = [
            GraphContextNode(
                entity_id=f"{knowledge_base_id}:{item.content_id}",
                entity_type="context_record",
                summary=f"Related to {item.content_id}",
            )
            for item in context_items
        ]
        edges = [
            GraphContextEdge(
                relationship_id=f"edge:{index}",
                relationship_type="supports_answer",
                source_id=nodes[index - 1].entity_id,
                target_id=nodes[index].entity_id,
                summary="Sequentially connected retrieved evidence.",
            )
            for index in range(1, len(nodes))
        ]
        summary = (
            f"Expanded {len(nodes)} graph nodes from retrieved evidence."
            if nodes
            else "Expanded 0 graph nodes from retrieved evidence."
        )
        return GraphContext(nodes=nodes, edges=edges, summary=summary)


class InMemoryAnswerGenerator:
    """A deterministic answer generator that echoes the question with context counts."""

    def __init__(self, *, provider: str = "in-memory", model_name: str = "in-memory-rag-model") -> None:
        self._provider = provider
        self._model_name = model_name

    def generate(self, request: RagGenerationRequest) -> RagGenerationResult:
        context_count = len(request.context_items)
        graph_clause = ""
        if request.graph_context is not None and request.graph_context.summary is not None:
            graph_clause = f" Graph: {request.graph_context.summary}"
        answer = f"Answer based on {context_count} context items: {request.question}.{graph_clause}".strip()
        return RagGenerationResult(
            request_id=request.request_id,
            answer=answer,
            provider=self._provider,
            model_name=self._model_name,
        )


def _matches_filters(
    record: ContextRecord,
    filters: dict[str, str | int | float | bool],
) -> bool:
    for key, value in filters.items():
        if record.metadata.get(key) != value:
            return False
    return True


def _embed_text(content: str) -> list[float]:
    text = content.strip()
    return [
        float(len(text)),
        float(sum(1 for char in text if char.isalpha())),
        float(sum(1 for char in text if char.isdigit())),
        float(len(text.split())),
    ]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Query vector dimensions must match stored context vectors.")
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=False))
    similarity = dot_product / (left_norm * right_norm)
    return max(-1.0, min(1.0, similarity))