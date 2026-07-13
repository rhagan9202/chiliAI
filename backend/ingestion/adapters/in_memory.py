"""In-memory document status store for tests and DB-less development."""

from __future__ import annotations

from ingestion.models import (
    STATUS_RANK,
    DocumentStatusTransition,
    IngestionStatus,
    SourceDocumentStatusRecord,
)

__all__ = ["InMemorySourceDocumentStatusStore"]

_Key = tuple[str, str]


class InMemorySourceDocumentStatusStore:
    """A dict-backed status store with the same monotonic semantics as Postgres."""

    def __init__(self) -> None:
        self._records: dict[_Key, SourceDocumentStatusRecord] = {}

    def apply(
        self, transition: DocumentStatusTransition
    ) -> SourceDocumentStatusRecord:
        key = (transition.knowledge_base_id, transition.source_document_id)
        new_rank = STATUS_RANK[transition.status]
        existing = self._records.get(key)
        if existing is None:
            record = SourceDocumentStatusRecord(
                knowledge_base_id=transition.knowledge_base_id,
                source_document_id=transition.source_document_id,
                current_status=transition.status,
                status_rank=new_rank,
                last_error=transition.error_message,
                dropped_entity_count=transition.dropped_entity_count or 0,
                dropped_relationship_count=(
                    transition.dropped_relationship_count or 0
                ),
                sample_reasons=list(transition.sample_reasons or []),
                first_event_at=transition.occurred_at,
                updated_at=transition.occurred_at,
            )
            self._records[key] = record
            return record
        advanced = new_rank > existing.status_rank
        record = existing.model_copy(
            update={
                "current_status": (
                    transition.status if advanced else existing.current_status
                ),
                "status_rank": max(existing.status_rank, new_rank),
                "last_error": (
                    transition.error_message
                    if advanced and transition.error_message is not None
                    else existing.last_error
                ),
                "dropped_entity_count": (
                    transition.dropped_entity_count
                    if transition.dropped_entity_count is not None
                    else existing.dropped_entity_count
                ),
                "dropped_relationship_count": (
                    transition.dropped_relationship_count
                    if transition.dropped_relationship_count is not None
                    else existing.dropped_relationship_count
                ),
                "sample_reasons": (
                    list(transition.sample_reasons)
                    if transition.sample_reasons is not None
                    else existing.sample_reasons
                ),
                "updated_at": max(existing.updated_at, transition.occurred_at),
            }
        )
        self._records[key] = record
        return record

    def get_many(
        self,
        *,
        knowledge_base_id: str,
        source_document_ids: list[str],
    ) -> dict[str, SourceDocumentStatusRecord]:
        found: dict[str, SourceDocumentStatusRecord] = {}
        for document_id in source_document_ids:
            record = self._records.get((knowledge_base_id, document_id))
            if record is not None:
                found[document_id] = record
        return found

    def list(
        self,
        *,
        knowledge_base_id: str,
        limit: int,
        offset: int,
        status: IngestionStatus | None = None,
    ) -> tuple[list[SourceDocumentStatusRecord], int]:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and (status is None or record.current_status == status)
        ]
        matches.sort(
            key=lambda record: (record.updated_at, record.source_document_id),
            reverse=True,
        )
        total = len(matches)
        if limit <= 0 or offset < 0:
            return [], total
        return matches[offset : offset + limit], total

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._records if key[0] == knowledge_base_id]
        for key in keys:
            del self._records[key]
        return len(keys)
