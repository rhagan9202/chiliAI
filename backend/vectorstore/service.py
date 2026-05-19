"""Service entry point for vectorstore indexing and search flows."""

from __future__ import annotations

from collections import Counter
import logging

from events.protocols import EventBus
from events.types import (
    VectorIndexedReference,
    VectorsDeletedEvent,
    VectorsIndexedEvent,
)
from shared.utils import generate_id
from storage.protocols import ObjectStore
from vectorstore.adapters.protocols import VectorStoreProtocol
from vectorstore.exceptions import VectorDimensionMismatchError, VectorStoreError
from vectorstore.models import VectorRecord
from vectorstore.service_models import (
    VectorAuditArtifact,
    VectorDeleteResponse,
    VectorIndexReceipt,
    VectorIndexRequest,
    VectorSearchMatch,
    VectorSearchRequest,
    VectorSearchResponse,
)


logger = logging.getLogger(__name__)


class VectorService:
    """Coordinate vector indexing and similarity search through injected ports."""

    # Add dimension pre-validation at service layer for clearer error messages.

    def __init__(
        self,
        store: VectorStoreProtocol,
        *,
        event_bus: EventBus,
        object_store: ObjectStore | None = None,
        max_batch_size: int = 500,
    ) -> None:
        if max_batch_size <= 0:
            raise ValueError("max_batch_size must be greater than 0.")
        self._store = store
        self._event_bus = event_bus
        self._object_store = object_store
        self._max_batch_size = max_batch_size

    def index(self, request: VectorIndexRequest) -> list[VectorIndexReceipt]:
        request_id = generate_id()
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
            stored_records = []
            for offset in range(0, len(records), self._max_batch_size):
                chunk = records[offset : offset + self._max_batch_size]
                stored_records.extend(
                    self._store.upsert_records(request.knowledge_base_id, chunk)
                )
        except VectorDimensionMismatchError:
            raise
        except ValueError as exc:
            raise VectorStoreError("Failed to index vector records.") from exc
        except Exception as exc:
            raise VectorStoreError("Failed to index vector records.") from exc

        expected_records = Counter(
            (record.id, record.content_id, record.knowledge_base_id)
            for record in records
        )
        actual_records = Counter(
            (record.id, record.content_id, record.knowledge_base_id)
            for record in stored_records
        )
        if actual_records != expected_records:
            missing = sorted(
                content_id
                for (_record_id, content_id, _knowledge_base_id), count in (
                    expected_records - actual_records
                ).items()
                for _ in range(count)
            )
            unexpected = sorted(
                content_id
                for (_record_id, content_id, _knowledge_base_id), count in (
                    actual_records - expected_records
                ).items()
                for _ in range(count)
            )
            details: list[str] = []
            if missing:
                details.append(f"missing records for: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected records for: {', '.join(unexpected)}")
            raise VectorStoreError(
                "Vector store returned incomplete batch results: "
                + "; ".join(details)
            )

        stored_by_id = {record.id: record for record in stored_records}
        receipts = [
            VectorIndexReceipt(
                knowledge_base_id=stored_by_id[record.id].knowledge_base_id,
                record_id=stored_by_id[record.id].id,
                content_id=stored_by_id[record.id].content_id,
                dimension=len(stored_by_id[record.id].embedding),
            )
            for record in records
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
        self._persist_audit_artifact(request_id, request.knowledge_base_id, receipts)
        return receipts

    def search(self, request: VectorSearchRequest) -> VectorSearchResponse:
        try:
            matches = self._store.search(
                request.knowledge_base_id,
                request.query_vector,
                request.limit,
                request.filters,
            )
        except VectorDimensionMismatchError:
            raise
        except ValueError as exc:
            raise VectorStoreError("Failed to search vector records.") from exc
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

    def batch_search(
        self, requests: list[VectorSearchRequest]
    ) -> list[VectorSearchResponse]:
        return [self.search(request) for request in requests]

    def get_record(
        self, knowledge_base_id: str, record_id: str
    ) -> VectorRecord | None:
        try:
            return self._store.get_record(knowledge_base_id, record_id)
        except Exception as exc:
            raise VectorStoreError("Failed to get vector record.") from exc

    def count(self, knowledge_base_id: str) -> int:
        try:
            return self._store.count_records(knowledge_base_id)
        except Exception as exc:
            raise VectorStoreError("Failed to count vector records.") from exc

    def delete_record(self, knowledge_base_id: str, record_id: str) -> bool:
        try:
            return self._store.delete_record(knowledge_base_id, record_id)
        except Exception as exc:
            raise VectorStoreError("Failed to delete vector record.") from exc

    def delete_knowledge_base(self, knowledge_base_id: str) -> VectorDeleteResponse:
        try:
            deleted_count = self._store.delete_namespace(knowledge_base_id)
        except Exception as exc:
            raise VectorStoreError("Failed to delete vector namespace.") from exc

        response = VectorDeleteResponse(
            knowledge_base_id=knowledge_base_id,
            deleted_count=deleted_count,
        )
        self._event_bus.publish(
            VectorsDeletedEvent(
                knowledge_base_id=knowledge_base_id,
                deleted_count=deleted_count,
            )
        )
        return response

    def _persist_audit_artifact(
        self,
        request_id: str,
        knowledge_base_id: str,
        receipts: list[VectorIndexReceipt],
    ) -> None:
        if self._object_store is None:
            return

        artifact = VectorAuditArtifact(
            request_id=request_id,
            knowledge_base_id=knowledge_base_id,
            receipts=receipts,
        )
        key = f"knowledgebases/{knowledge_base_id}/vector_index/{request_id}.json"
        try:
            self._object_store.put_bytes(
                key,
                artifact.model_dump_json().encode("utf-8"),
                media_type="application/json",
                metadata={
                    "knowledge_base_id": knowledge_base_id,
                    "request_id": request_id,
                    "receipt_count": len(receipts),
                },
            )
        except Exception:
            logger.warning(
                "Failed to persist vector index audit artifact",
                exc_info=True,
            )


def create_vector_service(
    store: VectorStoreProtocol,
    *,
    event_bus: EventBus,
    object_store: ObjectStore | None = None,
    max_batch_size: int = 500,
) -> VectorService:
    """Create the default vector service."""

    return VectorService(
        store,
        event_bus=event_bus,
        object_store=object_store,
        max_batch_size=max_batch_size,
    )


__all__ = ["VectorService", "create_vector_service"]
