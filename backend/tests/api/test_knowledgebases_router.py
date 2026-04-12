"""Tests for the knowledge base document registration route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_ingestion_service
from events.adapters.in_memory import InMemoryEventBus
from events.types import DocumentsUploadedEvent
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from storage.adapters.in_memory import InMemoryObjectStore


@pytest.fixture()
def client() -> tuple[TestClient, InMemoryEventBus]:
    app = create_app()
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
    app.dependency_overrides[get_ingestion_service] = lambda: service
    return TestClient(app), event_bus


def test_register_documents_returns_202_and_publishes_event(
    client: tuple[TestClient, InMemoryEventBus]
) -> None:
    test_client, event_bus = client

    response = test_client.post(
        "/knowledgebases/kb-1/documents",
        files=[("files", ("claims.json", b'{"claim_id": "42"}', "application/json"))],
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["documents"][0]["knowledge_base_id"] == "kb-1"
    assert isinstance(event_bus.published_events[0], DocumentsUploadedEvent)
    assert event_bus.published_events[0].event_type == "documents.uploaded"