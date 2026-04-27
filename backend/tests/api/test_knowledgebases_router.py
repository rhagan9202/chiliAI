"""Tests for the knowledgebases router."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api._kb_store import InMemoryKnowledgeBaseRepository
from api.app import create_app
from api.dependencies import (
    get_event_bus,
    get_ingestion_service,
    get_knowledge_base_repository,
    get_object_store,
)
from events.adapters.in_memory import InMemoryEventBus
from events.types import (
    DocumentsUploadedEvent,
    KnowledgeBaseCreatedEvent,
    KnowledgeBaseDeletedEvent,
)
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from storage.adapters.in_memory import InMemoryObjectStore


@pytest.fixture()
def harness() -> Iterator[
    tuple[TestClient, InMemoryEventBus, InMemoryObjectStore, InMemoryKnowledgeBaseRepository]
]:
    app = create_app()
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = InMemoryKnowledgeBaseRepository()
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service

    with TestClient(app) as client:
        yield client, event_bus, object_store, repository


def test_create_knowledge_base_returns_201_and_publishes_event(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, event_bus, _, _ = harness

    response = client.post(
        "/knowledgebases",
        json={"name": "Medicare Fraud", "description": "Initial KB"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Medicare Fraud"
    assert payload["description"] == "Initial KB"
    assert payload["id"]
    created_events = [
        event for event in event_bus.published_events
        if isinstance(event, KnowledgeBaseCreatedEvent)
    ]
    assert len(created_events) == 1
    assert created_events[0].knowledge_base_id == payload["id"]


def test_create_knowledge_base_allows_duplicate_names(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    first = client.post("/knowledgebases", json={"name": "shared", "description": ""})
    second = client.post("/knowledgebases", json={"name": "shared", "description": ""})

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_list_knowledge_bases_paginates_results(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    for index in range(3):
        client.post(
            "/knowledgebases",
            json={"name": f"kb-{index}", "description": "x"},
        )

    response = client.get("/knowledgebases", params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["items"]) == 2

    second_page = client.get("/knowledgebases", params={"limit": 2, "offset": 2})
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["total"] == 3
    assert len(second_payload["items"]) == 1


def test_get_knowledge_base_returns_404_when_missing(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    response = client.get("/knowledgebases/missing")

    assert response.status_code == 404


def test_get_knowledge_base_returns_record(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    created = client.post(
        "/knowledgebases", json={"name": "Read Back", "description": "y"}
    )
    kb_id = created.json()["id"]

    response = client.get(f"/knowledgebases/{kb_id}")

    assert response.status_code == 200
    assert response.json()["id"] == kb_id


def test_delete_knowledge_base_removes_artifacts_and_publishes_event(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, event_bus, object_store, _ = harness

    created = client.post(
        "/knowledgebases", json={"name": "ToDelete", "description": ""}
    )
    kb_id = created.json()["id"]

    object_store.put_bytes(
        f"knowledgebases/{kb_id}/documents/doc-1/file.json",
        b"{}",
        media_type="application/json",
    )
    object_store.put_bytes(
        f"knowledgebases/{kb_id}/parsed/parsed-1.json",
        b"{}",
        media_type="application/json",
    )
    object_store.put_bytes(
        "knowledgebases/other-kb/documents/doc-1/file.json",
        b"{}",
        media_type="application/json",
    )

    response = client.delete(f"/knowledgebases/{kb_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert object_store.list_keys(f"knowledgebases/{kb_id}/") == []
    assert object_store.exists("knowledgebases/other-kb/documents/doc-1/file.json")
    deletion_events = [
        event for event in event_bus.published_events
        if isinstance(event, KnowledgeBaseDeletedEvent)
    ]
    assert len(deletion_events) == 1
    assert deletion_events[0].knowledge_base_id == kb_id

    # Subsequent GET / DELETE should both be 404.
    assert client.get(f"/knowledgebases/{kb_id}").status_code == 404
    assert client.delete(f"/knowledgebases/{kb_id}").status_code == 404


def test_delete_knowledge_base_returns_404_when_missing(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, event_bus, _, _ = harness

    response = client.delete("/knowledgebases/missing")

    assert response.status_code == 404
    assert not any(
        isinstance(event, KnowledgeBaseDeletedEvent)
        for event in event_bus.published_events
    )


def test_register_documents_returns_202_and_publishes_event(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, event_bus, _, _ = harness

    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("claims.json", b'{"claim_id": "42"}', "application/json"))],
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["documents"][0]["knowledge_base_id"] == kb_id
    upload_events = [
        event for event in event_bus.published_events
        if isinstance(event, DocumentsUploadedEvent)
    ]
    assert upload_events
    assert upload_events[0].event_type == "documents.uploaded"


def test_list_documents_returns_404_for_missing_kb(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    response = client.get("/knowledgebases/missing/documents")

    assert response.status_code == 404


def test_list_documents_returns_paginated_summaries(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    created = client.post(
        "/knowledgebases", json={"name": "DocList", "description": ""}
    )
    kb_id = created.json()["id"]

    for index in range(2):
        client.post(
            f"/knowledgebases/{kb_id}/documents",
            files=[
                (
                    "files",
                    (f"file-{index}.json", b'{"x": 1}', "application/json"),
                )
            ],
        )

    response = client.get(
        f"/knowledgebases/{kb_id}/documents",
        params={"limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    summary = payload["items"][0]
    assert summary["filename"] == "file-0.json"
    assert summary["content_type"] == "application/json"
    assert summary["size_bytes"] == len(b'{"x": 1}')
    assert summary["status"]
    assert summary["created_at"]


def test_delete_document_removes_artifacts(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, object_store, _ = harness

    created = client.post(
        "/knowledgebases", json={"name": "DocDelete", "description": ""}
    )
    kb_id = created.json()["id"]

    upload = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("victim.json", b'{"x": 1}', "application/json"))],
    )
    document_id = upload.json()["documents"][0]["source_document_id"]
    assert object_store.list_keys(
        f"knowledgebases/{kb_id}/documents/{document_id}/"
    )

    response = client.delete(
        f"/knowledgebases/{kb_id}/documents/{document_id}"
    )

    assert response.status_code == 204
    assert (
        object_store.list_keys(
            f"knowledgebases/{kb_id}/documents/{document_id}/"
        )
        == []
    )
    assert (
        client.delete(f"/knowledgebases/{kb_id}/documents/{document_id}").status_code
        == 404
    )


def test_delete_document_returns_404_for_missing_kb(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    response = client.delete("/knowledgebases/missing/documents/anything")

    assert response.status_code == 404
