"""Durable per-document status projection from pipeline events (BL-041).

Maps the four subscribed event types onto monotonic ``IngestionStatus``
transitions. ``EXTRACTED_EMPTY`` is intentionally a *status transition*
derived from the existing ``DocumentsExtractionWarningEvent`` — no new event
type exists, and the event codec registry is untouched.
"""

from __future__ import annotations

from events.types import (
    AnyEvent,
    DocumentsExtractionWarningEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
)
from ingestion.adapters.protocols import SourceDocumentStatusStore
from ingestion.models import DocumentStatusTransition, IngestionStatus

__all__ = ["project_document_status"]


def project_document_status(
    event: AnyEvent,
    status_store: SourceDocumentStatusStore,
) -> int:
    """Apply status transitions for a pipeline event; return the count applied."""

    transitions = _transitions_for_event(event)
    for transition in transitions:
        status_store.apply(transition)
    return len(transitions)


def _transitions_for_event(event: AnyEvent) -> list[DocumentStatusTransition]:
    if isinstance(event, DocumentsUploadedEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=IngestionStatus.PENDING,
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    if isinstance(event, DocumentsParsedEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=IngestionStatus.PARSED,
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    if isinstance(event, DocumentsFailedEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=IngestionStatus.FAILED,
                error_message=document.error_message,
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    if isinstance(event, DocumentsExtractionWarningEvent):
        return [
            DocumentStatusTransition(
                knowledge_base_id=document.knowledge_base_id,
                source_document_id=document.source_document_id,
                status=(
                    IngestionStatus.EXTRACTED_EMPTY
                    if document.empty_extraction
                    else IngestionStatus.VALIDATED
                ),
                dropped_entity_count=document.dropped_entity_count,
                dropped_relationship_count=document.dropped_relationship_count,
                sample_reasons=list(document.sample_reasons),
                occurred_at=event.occurred_at,
            )
            for document in event.documents
        ]
    return []
