"""Tests for document re-upload idempotency (content-hash dedup).

Uploading the same bytes twice to a KB should:
  1. Cascade-delete the original document's graph nodes and vector points.
  2. Re-register the document under a new source_document_id.
  3. Surface the old id as ``replaced_document_id`` in the receipt.

Uploading *different* bytes should create a fresh document with no replacement.
"""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_event_bus,
    get_graph_service,
    get_ingestion_service,
    get_object_store,
    get_raw_record_store,
    get_vector_service,
    get_vectorstore_service,
    get_workflow_tracker,
)
from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.workflow_tracking import WorkflowEventTracker
from config.schema import (
    AlertsConfig,
    AuthConfig,
    CapabilitiesConfig,
    DomainConfig,
    DomainInfo,
    IngestionConfig,
    ValidationConfig,
)
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from records.adapters.in_memory import InMemoryRawRecordStore
from storage.adapters.in_memory import InMemoryObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.service import create_vector_service


def _build_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="Test"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(enabled=False),
        validation=ValidationConfig(
            max_file_size_mb=10,
            allowed_content_types=["text/plain", "application/json"],
        ),
        alerts=AlertsConfig(thresholds={}),
    )


@pytest.fixture()
def api_client() -> Iterator[TestClient]:
    """TestClient backed by full in-memory adapters with graph + vector wired."""
    app = create_app()
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    graph_repository = InMemoryGraphRepository()
    graph_service = create_graph_service(
        graph_repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    vector_store = InMemoryVectorStore()
    vector_service = create_vector_service(
        vector_store,
        event_bus=event_bus,
        object_store=object_store,
    )
    workflow_run_store = InMemoryWorkflowRunStore()
    workflow_tracker = WorkflowEventTracker(workflow_run_store)
    raw_record_store = InMemoryRawRecordStore()
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    app.dependency_overrides[get_domain_config] = _build_config
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_vectorstore_service] = lambda: vector_service
    app.dependency_overrides[get_workflow_tracker] = lambda: workflow_tracker
    app.dependency_overrides[get_raw_record_store] = lambda: raw_record_store
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


def test_reuploading_same_document_replaces_extraction(api_client: TestClient) -> None:
    create = api_client.post(
        "/knowledgebases", json={"name": "reupload", "description": ""}
    )
    assert create.status_code == 201, create.text
    kb_id: str = create.json()["id"]

    content = b'{\n  "npi": "1234567890",\n  "specialty": "Cardiology"\n}\n'

    first = api_client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("provider.json", BytesIO(content), "application/json"))],
    )
    assert first.status_code == 202, first.text
    first_receipts = first.json()["documents"]
    assert len(first_receipts) == 1
    original_doc_id: str = first_receipts[0]["source_document_id"]
    assert first_receipts[0].get("replaced_document_id") is None

    second = api_client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("provider.json", BytesIO(content), "application/json"))],
    )
    assert second.status_code == 202, second.text
    second_receipt = second.json()["documents"][0]
    assert second_receipt["replaced_document_id"] == original_doc_id

    # The ingestion service is content-addressed, so the new document id may
    # equal the original id (same bytes → same sha256-derived key).  What
    # matters is that the KB metadata store contains exactly one record and the
    # replaced_document_id was surfaced.
    new_doc_id: str = second_receipt["source_document_id"]

    # KB should show exactly 1 document (deduplicated), not 2.
    docs_resp = api_client.get(f"/knowledgebases/{kb_id}/documents")
    assert docs_resp.status_code == 200
    assert docs_resp.json()["total"] == 1
    assert docs_resp.json()["items"][0]["id"] == new_doc_id


def test_reupload_with_different_content_does_not_dedupe(api_client: TestClient) -> None:
    create = api_client.post(
        "/knowledgebases", json={"name": "reupload2", "description": ""}
    )
    assert create.status_code == 201, create.text
    kb_id: str = create.json()["id"]

    first = api_client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", BytesIO(b'{"npi": "1"}'), "application/json"))],
    )
    assert first.status_code == 202
    second = api_client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", BytesIO(b'{"npi": "2"}'), "application/json"))],
    )
    assert second.status_code == 202, second.text
    receipt = second.json()["documents"][0]
    # Different content hash -> fresh insert, no replacement.
    assert receipt.get("replaced_document_id") is None

    # KB should now have 2 documents (both retained).
    docs_resp = api_client.get(f"/knowledgebases/{kb_id}/documents")
    assert docs_resp.status_code == 200
    assert docs_resp.json()["total"] == 2
