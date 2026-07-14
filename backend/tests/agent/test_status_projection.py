"""Event-to-status-transition mapping for the document projection (BL-041)."""

from __future__ import annotations

from agent.status_projection import project_document_status
from events.types import (
    DocumentFailureReference,
    DocumentReference,
    DocumentsExtractionWarningEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    ExtractionWarningReference,
    KnowledgeBaseCreatedEvent,
    ParsedDocumentReference,
)
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.models import IngestionStatus


def _get(store: InMemorySourceDocumentStatusStore, doc: str = "doc-1"):
    return store.get_many(knowledge_base_id="kb-1", source_document_ids=[doc])[doc]


def test_uploaded_projects_pending() -> None:
    store = InMemorySourceDocumentStatusStore()
    applied = project_document_status(
        DocumentsUploadedEvent(
            documents=[
                DocumentReference(
                    knowledge_base_id="kb-1", source_document_id="doc-1"
                )
            ]
        ),
        store,
    )
    assert applied == 1
    assert _get(store).current_status == IngestionStatus.PENDING


def test_parsed_projects_parsed() -> None:
    store = InMemorySourceDocumentStatusStore()
    applied = project_document_status(
        DocumentsParsedEvent(
            documents=[
                ParsedDocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    parsed_document_id="parsed-1",
                    parser_name="test",
                )
            ]
        ),
        store,
    )
    assert applied == 1
    assert _get(store).current_status == IngestionStatus.PARSED


def test_failed_projects_failed_with_error() -> None:
    store = InMemorySourceDocumentStatusStore()
    project_document_status(
        DocumentsFailedEvent(
            documents=[
                DocumentFailureReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    error_message="parser exploded",
                )
            ]
        ),
        store,
    )
    record = _get(store)
    assert record.current_status == IngestionStatus.FAILED
    assert record.last_error == "parser exploded"


def test_empty_extraction_warning_projects_extracted_empty_status() -> None:
    store = InMemorySourceDocumentStatusStore()
    project_document_status(
        DocumentsExtractionWarningEvent(
            documents=[
                ExtractionWarningReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    valid_entity_count=0,
                    valid_relationship_count=0,
                    dropped_entity_count=4,
                    dropped_relationship_count=2,
                    stripped_property_count=0,
                    empty_extraction=True,
                    sample_reasons=["entity cand-1: unknown type"],
                )
            ]
        ),
        store,
    )
    record = _get(store)
    assert record.current_status == IngestionStatus.EXTRACTED_EMPTY
    assert record.dropped_entity_count == 4
    assert record.dropped_relationship_count == 2
    assert record.sample_reasons == ["entity cand-1: unknown type"]


def test_non_empty_warning_projects_validated_with_counts() -> None:
    store = InMemorySourceDocumentStatusStore()
    project_document_status(
        DocumentsExtractionWarningEvent(
            documents=[
                ExtractionWarningReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                    valid_entity_count=7,
                    valid_relationship_count=3,
                    dropped_entity_count=2,
                    dropped_relationship_count=0,
                    stripped_property_count=1,
                    empty_extraction=False,
                    sample_reasons=["entity cand-9: missing required field"],
                )
            ]
        ),
        store,
    )
    record = _get(store)
    assert record.current_status == IngestionStatus.VALIDATED
    assert record.dropped_entity_count == 2
    assert record.sample_reasons == ["entity cand-9: missing required field"]


def test_unrelated_event_projects_nothing() -> None:
    store = InMemorySourceDocumentStatusStore()
    applied = project_document_status(
        KnowledgeBaseCreatedEvent(knowledge_base_id="kb-1"), store
    )
    assert applied == 0
    assert store.list(knowledge_base_id="kb-1", limit=10, offset=0) == ([], 0)
