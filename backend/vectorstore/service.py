"""Service entry point for vectorstore indexing and search flows."""

from __future__ import annotations

from events.protocols import EventBus
from events.types import VectorIndexedReference, VectorsIndexedEvent
from shared.utils import generate_id
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.exceptions import VectorDimensionMismatchError, VectorStoreError
from vectorstore.models import VectorRecord
from vectorstore.service_models import (
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorSearchMatch,
    VectorSearchRequest,
    VectorSearchResponse,
)


class VectorService:
    """Coordinate vector indexing and similarity search through injected ports."""

    def __init__(self, store: VectorStoreProtocol, *, event_bus: EventBus) -> None:
        self._store = store
        self._event_bus = event_bus

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]:
        records = [
            VectorRecord(
                id=generate_id(),
                knowledge_base_id=request.knowledge_base_id,
                content_id=submission.content_id,
                embedding=list(submission.embedding),
                content=submission.content,
                metadata=dict(submission.metadata),
            )
            for submission in request.submissions
        ]
        try:
            stored_records = self._store.upsert_records(request.knowledge_base_id, records)
        except ValueError as exc:
            raise VectorDimensionMismatchError(str(exc)) from exc
        except Exception as exc:
            raise VectorStoreError("Failed to index vector records.") from exc

        receipts = [
            VectorIndexReceipt(
                knowledge_base_id=record.knowledge_base_id,
                record_id=record.id,
                content_id=record.content_id,
                dimension=len(record.embedding),
            )
            for record in stored_records
        ]
        self._event_bus.publish(
            VectorsIndexedEvent(
                records=[
                    VectorIndexedReference(
                        knowledge_base_id=receipt.knowledge_base_id,
                        record_id=receipt.record_id,
                        content_id=receipt.content_id,
                        dimension=receipt.dimension,
                    )
                    for receipt in receipts
                ]
            )
        )
        return receipts

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse:
        try:
            matches = self._store.search(
                request.knowledge_base_id,
                request.query_vector,
                request.limit,
                request.filters,
            )
        except ValueError as exc:
            raise VectorDimensionMismatchError(str(exc)) from exc
        except Exception as exc:
            raise VectorStoreError("Failed to search vector records.") from exc

        return VectorSearchResponse(
            knowledge_base_id=request.knowledge_base_id,
            query_dimension=len(request.query_vector),
            matches=[
                VectorSearchMatch(
                    record_id=match.record_id,
                    content_id=match.content_id,
                    score=match.score,
                    content=match.content,
                    metadata=dict(match.metadata),
                )
                for match in matches
            ],
        )


def create_vector_service(store: VectorStoreProtocol, *, event_bus: EventBus) -> VectorService:
    """Create the default vector service."""

    return VectorService(store, event_bus=event_bus)


__all__ = ["VectorService", "create_vector_service"]