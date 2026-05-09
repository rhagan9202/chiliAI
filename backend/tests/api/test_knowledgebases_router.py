"""Tests for the knowledge base manager routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_api_state
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
    get_api_state.cache_clear()
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
    test_client = TestClient(app)
    try:
        yield test_client, event_bus
    finally:
        get_api_state.cache_clear()


def test_list_knowledge_bases_returns_seeded_inventory(
    client: tuple[TestClient, InMemoryEventBus]
) -> None:
    test_client, _ = client

    response = test_client.get("/knowledgebases")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["total_items"] >= 2
    assert payload["items"][0]["document_count"] >= 1


def test_create_and_delete_knowledge_base_updates_collection(
    client: tuple[TestClient, InMemoryEventBus]
) -> None:
    test_client, _ = client

    created = test_client.post(
        "/knowledgebases",
        json={"name": "Policy Sandbox", "description": "Ad hoc KB for new policy uploads."},
    )

    assert created.status_code == 200
    knowledge_base_id = created.json()["knowledge_base"]["id"]

    detail = test_client.get(f"/knowledgebases/{knowledge_base_id}")
    assert detail.status_code == 200
    assert detail.json()["knowledge_base"]["name"] == "Policy Sandbox"

    deleted = test_client.delete(f"/knowledgebases/{knowledge_base_id}")
    assert deleted.status_code == 200

    collection = test_client.get("/knowledgebases").json()["items"]
    assert all(item["id"] != knowledge_base_id for item in collection)


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

    inventory = test_client.get("/knowledgebases/kb-1/documents")
    assert inventory.status_code == 200
    assert any(item["filename"] == "claims.json" for item in inventory.json()["items"])


def test_document_status_and_delete_endpoints_reflect_inventory_state(
    client: tuple[TestClient, InMemoryEventBus]
) -> None:
    test_client, _ = client

    inventory = test_client.get("/knowledgebases/kb-1/documents")
    assert inventory.status_code == 200
    document_id = inventory.json()["items"][0]["id"]

    status_response = test_client.get(f"/knowledgebases/kb-1/documents/{document_id}/status")
    assert status_response.status_code == 200
    assert len(status_response.json()["timeline"]) >= 1

    deleted = test_client.delete(f"/knowledgebases/kb-1/documents/{document_id}")
    assert deleted.status_code == 200

    remaining = test_client.get("/knowledgebases/kb-1/documents").json()["items"]
    assert all(item["id"] != document_id for item in remaining)


def test_rebuild_endpoint_returns_queued_workflow(
    client: tuple[TestClient, InMemoryEventBus]
) -> None:
    test_client, _ = client

    response = test_client.post("/knowledgebases/kb-1/rebuild")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_type"] == "graph_build"
    assert payload["status"] == "queued"