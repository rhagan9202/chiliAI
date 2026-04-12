"""Tests for the worker coordinator ingestion wiring."""

from __future__ import annotations

from agent.coordinator import drain_ingestion_events
from events.adapters.in_memory import InMemoryEventBus
from events.types import DocumentsParsedEvent, DocumentsUploadedEvent
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.service_models import DocumentSubmission
from storage.adapters.in_memory import InMemoryObjectStore


def test_drain_ingestion_events_processes_uploaded_documents() -> None:
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

    service.register_documents(
        "kb-1",
        [
            DocumentSubmission(
                filename="claims.json",
                content=b'{"claim_id": "42"}',
                content_type="application/json",
            )
        ],
    )

    processed = drain_ingestion_events(
        event_bus,
        service,
        consumer_group="test-workers",
        consumer_name="worker-1",
    )

    assert processed == 1
    assert any(isinstance(event, DocumentsParsedEvent) for event in event_bus.published_events)