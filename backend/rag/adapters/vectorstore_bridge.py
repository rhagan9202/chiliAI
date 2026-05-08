"""Production context retriever adapter that delegates to the vectorstore service."""

from __future__ import annotations

from rag.models import MetadataValue, RetrievedContextItem
from vectorstore.protocols import VectorServiceProtocol
from vectorstore.service_models import VectorSearchRequest


class ServiceContextRetriever:
    """Adapter that satisfies `ContextRetrieverProtocol` via `VectorServiceProtocol`."""

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


__all__ = ["ServiceContextRetriever"]
