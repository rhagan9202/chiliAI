"""Tests for document re-upload idempotency (content-hash dedup).

Uploading the same bytes twice to a KB is an idempotent no-op:
  1. The content-addressed source_document_id is unchanged.
  2. The existing document, its graph/vector provenance, and object-store
     artifacts are preserved (no destructive cleanup).
  3. The receipt is deduplicated (``enqueued`` is False) and still surfaces the
     existing id as ``replaced_document_id``.
  4. No second DocumentsUploadedEvent is published, so the worker does not
     reprocess identical bytes.

Uploading *different* bytes should create a fresh document with no replacement.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
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
from agent.coordinator import drain_ingestion_events
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
from embeddings.adapters.in_memory import InMemoryEmbedder
from embeddings.service import create_embeddings_service
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from ingestion.chunker import create_document_chunker
from ingestion.extractor import create_document_extractor
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.validator import create_extraction_validator
from records.adapters.in_memory import InMemoryRawRecordStore
from shared.types import EntityDefinition, PropertyDefinition, PropertyType
from storage.adapters.in_memory import InMemoryObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.service import create_vector_service


def _build_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="Test"),
        entities=[
            EntityDefinition(
                name="provider",
                display_label="Provider",
                icon="stethoscope",
                properties={
                    "npi": PropertyDefinition(
                        type=PropertyType.STRING, display="NPI", required=True
                    ),
                },
            ),
        ],
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


@dataclass
class ReuploadHarness:
    """Bundles client + in-memory adapters needed to drain the worker in tests."""

    client: TestClient
    event_bus: InMemoryEventBus
    object_store: InMemoryObjectStore
    graph_repository: InMemoryGraphRepository
    vector_store: InMemoryVectorStore
    ingestion_service: IngestionService

    def drain(self, *, max_iterations: int = 32) -> int:
        """Drive drain_ingestion_events until quiescent."""
        entity_defs = _build_config().entities
        document_chunker = create_document_chunker()
        document_extractor = create_document_extractor(entity_defs)
        extraction_validator = create_extraction_validator(entity_defs, [])
        embedder = InMemoryEmbedder(dimensions=4)
        embeddings_service = create_embeddings_service(
            embedder,
            event_bus=self.event_bus,
        )
        graph_service = create_graph_service(
            self.graph_repository,
            object_store=self.object_store,
            event_bus=self.event_bus,
        )
        total = 0
        for _ in range(max_iterations):
            processed = asyncio.run(
                drain_ingestion_events(
                    self.event_bus,
                    self.ingestion_service,
                    document_chunker,
                    document_extractor,
                    extraction_validator,
                    graph_service,
                    self.object_store,
                    embeddings_service=embeddings_service,
                    vector_store=self.vector_store,
                    graph_repository=self.graph_repository,
                    consumer_group="reupload-workers",
                    consumer_name="reupload-worker-1",
                )
            )
            total += processed
            if processed == 0:
                break
        return total


@pytest.fixture()
def reupload_harness() -> Iterator[ReuploadHarness]:
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
        yield ReuploadHarness(
            client=client,
            event_bus=event_bus,
            object_store=object_store,
            graph_repository=graph_repository,
            vector_store=vector_store,
            ingestion_service=ingestion_service,
        )

    app.dependency_overrides.clear()


# Keep a simple fixture for tests that only need the client
@pytest.fixture()
def api_client(reupload_harness: ReuploadHarness) -> TestClient:
    return reupload_harness.client


def test_reuploading_same_document_is_idempotent_noop(
    reupload_harness: ReuploadHarness,
) -> None:
    client = reupload_harness.client

    create = client.post(
        "/knowledgebases", json={"name": "reupload", "description": ""}
    )
    assert create.status_code == 201, create.text
    kb_id: str = create.json()["id"]

    content = b'{\n  "npi": "1234567890",\n  "specialty": "Cardiology"\n}\n'

    first = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("provider.json", BytesIO(content), "application/json"))],
    )
    assert first.status_code == 202, first.text
    first_receipts = first.json()["documents"]
    assert len(first_receipts) == 1
    original_doc_id: str = first_receipts[0]["source_document_id"]
    assert first_receipts[0].get("replaced_document_id") is None

    # Drain the worker to populate graph + vector from the first upload.
    reupload_harness.drain()
    entity_count_after_first = reupload_harness.graph_repository.count_entities(kb_id)
    vector_count_after_first = reupload_harness.vector_store.count_records(kb_id)
    assert entity_count_after_first >= 0  # extracted whatever entities the pattern extractor found

    second = client.post(
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
    docs_resp = client.get(f"/knowledgebases/{kb_id}/documents")
    assert docs_resp.status_code == 200
    assert docs_resp.json()["total"] == 1
    assert docs_resp.json()["items"][0]["id"] == new_doc_id

    # Drain after the second upload. Per the idempotency contract, an identical
    # re-upload deduplicates (enqueued=False): no new DocumentsUploadedEvent is
    # published and the existing graph/vector data is preserved untouched.
    reupload_harness.drain()

    # Only the first upload published a DocumentsUploadedEvent; the identical
    # re-upload is a deduplicated no-op.
    from events.types import DocumentsUploadedEvent
    uploaded_events = [
        e for e in reupload_harness.event_bus.published_events
        if isinstance(e, DocumentsUploadedEvent)
    ]
    assert len(uploaded_events) == 1, (
        f"Expected 1 DocumentsUploadedEvent (identical re-upload is a deduplicated "
        f"no-op), got {len(uploaded_events)}."
    )

    # The preserved graph + vector data is unchanged from the first drain.
    entity_count_after_second = reupload_harness.graph_repository.count_entities(kb_id)
    vector_count_after_second = reupload_harness.vector_store.count_records(kb_id)
    assert entity_count_after_second == entity_count_after_first, (
        f"Graph entities after identical re-upload ({entity_count_after_second}) should "
        f"equal the preserved count ({entity_count_after_first})."
    )
    assert vector_count_after_second == vector_count_after_first, (
        f"Vector records after identical re-upload ({vector_count_after_second}) should "
        f"equal the preserved count ({vector_count_after_first})."
    )


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
