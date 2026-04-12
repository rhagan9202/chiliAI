"""Tests for the ingestion service entry point."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import DocumentReference, DocumentsFailedEvent, DocumentsParsedEvent, DocumentsUploadedEvent
from ingestion.models import SourceDocument, SourceType
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.service_models import DocumentSubmission, IngestionTask
from storage.adapters.in_memory import InMemoryObjectStore


def _service() -> tuple[IngestionService, InMemoryEventBus, InMemoryObjectStore]:
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )
    return service, event_bus, object_store


def test_register_documents_stores_content_and_publishes_event() -> None:
    service, event_bus, object_store = _service()

    receipts = service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    assert len(receipts) == 1
    assert receipts[0].storage_key is not None
    stored = object_store.get_bytes(receipts[0].storage_key or "")
    assert stored.content == b'{"claim_id": "42"}'
    assert isinstance(event_bus.published_events[0], DocumentsUploadedEvent)
    assert event_bus.published_events[0].event_type == "documents.uploaded"


def test_ingest_task_parses_stored_document_and_publishes_parsed_event() -> None:
    service, event_bus, object_store = _service()
    storage_key = "knowledgebases/kb-1/documents/doc-1/claims.json"
    object_store.put_bytes(storage_key, b'{"claim_id": "42"}', media_type="application/json")

    outcome = service.ingest_task(
        IngestionTask(
            knowledge_base_id="kb-1",
            source_document=SourceDocument(
                id="doc-1",
                source_type=SourceType.FILE_UPLOAD,
                filename="claims.json",
            ),
            storage_key=storage_key,
            content_type="application/json",
        )
    )

    assert isinstance(event_bus.published_events[-1], DocumentsParsedEvent)
    assert outcome.parsed_document.records[0].fields["claim_id"] == "42"  # type: ignore[union-attr]


def test_process_documents_uploaded_publishes_failure_for_unresolved_format() -> None:
    service, event_bus, _object_store = _service()
    uploaded = DocumentsUploadedEvent(
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-failed",
                filename=None,
                content_type=None,
                storage_key=None,
                uri=None,
                document_format=None,
                size_bytes=None,
            )
        ]
    )

    outcomes = service.process_documents_uploaded(uploaded)

    assert len(outcomes) == 1
    assert isinstance(event_bus.published_events[-1], DocumentsFailedEvent)
    assert outcomes[0].error_type == "RemoteFetchError"  # type: ignore[union-attr]