"""Tests for the knowledgebases router."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from typing import cast

import anyio
import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.adapters.object_store import ObjectStoreKnowledgeBaseRepository
from knowledgebases.models import DocumentRecord
from api.app import create_app
from api.dependencies import (
    get_document_status_store,
    get_event_bus,
    get_domain_config,
    get_graph_service,
    get_ingestion_service,
    get_knowledge_base_repository,
    get_object_store,
    get_vector_service,
)
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
from events.types import (
    DocumentsUploadedEvent,
    KnowledgeBaseCreatedEvent,
    KnowledgeBaseDeletedEvent,
)
from ingestion.adapters.in_memory import InMemorySourceDocumentStatusStore
from ingestion.models import DocumentStatusTransition, IngestionStatus
from ingestion.orchestrators.parser import DocumentParsingOrchestrator
from ingestion.parsers.registry import create_default_registry
from ingestion.parsers.remote import HttpxRemoteDocumentFetcher
from ingestion.service import IngestionService
from ingestion.service_models import DocumentReceipt, DocumentSubmission
from graph.models import GraphDeleteByProvenance, GraphMetrics
from shared.types import KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore
from api.routers.knowledgebases import read_upload_file_with_limit
from vectorstore.service_models import VectorDeleteResponse


def _build_config() -> DomainConfig:
    return DomainConfig(
        domain=DomainInfo(name="test", display_name="Test", description="Test"),
        entities=[],
        relationships=[],
        capabilities=CapabilitiesConfig(),
        ingestion=IngestionConfig(sources=[]),
        auth=AuthConfig(enabled=False),
        validation=ValidationConfig(
            max_file_size_mb=1,
            allowed_content_types=["text/plain", "application/json"],
        ),
        alerts=AlertsConfig(thresholds={}),
    )


class _MetricsOnlyGraphService:
    def __init__(self, metrics: GraphMetrics) -> None:
        self._metrics = metrics
        self.deleted_knowledge_base_ids: list[str] = []

    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics:
        del knowledge_base_id
        return self._metrics

    def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        self.deleted_knowledge_base_ids.append(knowledge_base_id)


class _RecordingReplacementGraphService(_MetricsOnlyGraphService):
    def __init__(self) -> None:
        super().__init__(
            GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)
        )
        self.source_documents: set[tuple[str, str]] = set()
        self.deleted_source_documents: list[tuple[str, str]] = []

    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance:
        self.deleted_source_documents.append((knowledge_base_id, source_document_id))
        self.source_documents.discard((knowledge_base_id, source_document_id))
        return GraphDeleteByProvenance(
            knowledge_base_id=knowledge_base_id,
            source_document_id=source_document_id,
            entity_count=1,
            relationship_count=0,
        )


class _RecordingReplacementVectorService:
    def __init__(self) -> None:
        self.source_documents: set[tuple[str, str]] = set()
        self.deleted_source_documents: list[tuple[str, str]] = []

    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> VectorDeleteResponse:
        self.deleted_source_documents.append((knowledge_base_id, source_document_id))
        self.source_documents.discard((knowledge_base_id, source_document_id))
        return VectorDeleteResponse(knowledge_base_id=knowledge_base_id, deleted_count=1)


def _skip_policy_audit(app: FastAPI) -> None:
    del app


@pytest.fixture()
def harness() -> Iterator[
    tuple[TestClient, InMemoryEventBus, InMemoryObjectStore, InMemoryKnowledgeBaseRepository]
]:
    app = create_app()
    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    repository = InMemoryKnowledgeBaseRepository()
    graph_service = _MetricsOnlyGraphService(
        GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)
    )
    ingestion_service = IngestionService(
        DocumentParsingOrchestrator(
            create_default_registry(),
            fetcher=HttpxRemoteDocumentFetcher(),
        ),
        object_store=object_store,
        event_bus=event_bus,
    )

    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_domain_config] = _build_config
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
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


def test_object_store_repository_persists_kb_metadata_across_instances() -> None:
    object_store = InMemoryObjectStore()
    first_repository = ObjectStoreKnowledgeBaseRepository(object_store)
    created_at = utc_now()

    first_repository.create(
        KnowledgeBase(
            id="kb-persisted",
            name="Persistent KB",
            description="Survives API reloads",
            created_at=created_at,
        )
    )
    first_repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-persisted",
            filename="claims.json",
            content_type="application/json",
            size_bytes=2,
            status="registered",
            storage_key="knowledgebases/kb-persisted/documents/doc-1/source.json",
        )
    )

    second_repository = ObjectStoreKnowledgeBaseRepository(object_store)

    persisted = second_repository.get("kb-persisted")
    assert persisted is not None
    assert persisted.name == "Persistent KB"
    assert persisted.document_count == 1

    items, total = second_repository.list(limit=10, offset=0)
    assert total == 1
    assert [item.id for item in items] == ["kb-persisted"]

    documents, document_total = second_repository.list_documents(
        "kb-persisted",
        limit=10,
        offset=0,
    )
    assert document_total == 1
    assert documents[0].filename == "claims.json"


def test_object_store_repository_persists_deletions_across_instances() -> None:
    object_store = InMemoryObjectStore()
    first_repository = ObjectStoreKnowledgeBaseRepository(object_store)
    first_repository.create(
        KnowledgeBase(
            id="kb-delete",
            name="Delete KB",
            description="",
            created_at=utc_now(),
        )
    )
    first_repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-delete",
            filename="claims.json",
        )
    )

    assert first_repository.delete_document("kb-delete", "doc-1") is True
    assert first_repository.delete("kb-delete") is True

    second_repository = ObjectStoreKnowledgeBaseRepository(object_store)
    assert second_repository.get("kb-delete") is None
    items, total = second_repository.list(limit=10, offset=0)
    assert items == []
    assert total == 0


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


def test_get_knowledge_base_hydrates_ready_status_from_graph_metrics() -> None:
    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    object_store = InMemoryObjectStore()
    repository.create(
        KnowledgeBase(
            id="kb-ready",
            name="Ready KB",
            description="",
            status="active",
            created_at=utc_now(),
        )
    )
    repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-ready",
            filename="claims.json",
            content_type="application/json",
            size_bytes=2,
            status="pending",
            storage_key="knowledgebases/kb-ready/documents/doc-1/source.json",
        )
    )
    repository.record_document_warnings(
        "kb-ready",
        "doc-1",
        additional_count=2,
        reasons=["csv.ragged_row: row 1 dropped a field"],
    )
    graph_service = _MetricsOnlyGraphService(
        GraphMetrics(entity_count=4, relationship_count=4, avg_degree=2.0)
    )
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_domain_config] = _build_config

    with TestClient(app) as client:
        detail = client.get("/knowledgebases/kb-ready")
        documents = client.get("/knowledgebases/kb-ready/documents")

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["status"] == "ready"
    assert detail_payload["entity_count"] == 4
    assert detail_payload["relationship_count"] == 4
    persisted = repository.get("kb-ready")
    assert persisted is not None
    assert persisted.status == "ready"
    assert persisted.entity_count == 4
    assert persisted.relationship_count == 4

    assert documents.status_code == 200
    document_payload = documents.json()
    assert document_payload["items"][0]["status"] == "ready"
    assert document_payload["items"][0]["warning_count"] == 2
    assert document_payload["items"][0]["warning_reasons"] == [
        "csv.ragged_row: row 1 dropped a field"
    ]
    persisted_document = repository.get_document("kb-ready", "doc-1")
    assert persisted_document is not None
    assert persisted_document.status == "ready"


def test_get_knowledge_base_marks_zero_entity_graph_update_ready() -> None:
    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    object_store = InMemoryObjectStore()
    repository.create(
        KnowledgeBase(
            id="kb-empty-graph",
            name="Empty Graph KB",
            description="",
            status="active",
            created_at=utc_now(),
        )
    )
    repository.add_document(
        DocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-empty-graph",
            filename="resume.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=2,
            status="pending",
            storage_key="knowledgebases/kb-empty-graph/documents/doc-1/source.docx",
        )
    )
    object_store.put_bytes(
        "knowledgebases/kb-empty-graph/graph_updates/extract-1.json",
        b"{}",
        media_type="application/json",
    )
    graph_service = _MetricsOnlyGraphService(
        GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)
    )
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_domain_config] = _build_config

    with TestClient(app) as client:
        detail = client.get("/knowledgebases/kb-empty-graph")
        documents = client.get("/knowledgebases/kb-empty-graph/documents")

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["status"] == "ready"
    assert detail_payload["entity_count"] == 0
    assert detail_payload["relationship_count"] == 0

    assert documents.status_code == 200
    assert documents.json()["items"][0]["status"] == "ready"


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


def test_delete_knowledge_base_retries_pending_cleanup_kb(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, event_bus, object_store, repository = harness

    created = client.post(
        "/knowledgebases", json={"name": "PendingCleanup", "description": ""}
    )
    kb_id = created.json()["id"]
    object_store.put_bytes(
        f"knowledgebases/{kb_id}/documents/doc-1/file.json",
        b"{}",
        media_type="application/json",
    )
    repository.mark_pending_cleanup(kb_id)

    response = client.delete(f"/knowledgebases/{kb_id}")

    assert response.status_code == 204
    assert repository.get(kb_id) is None
    assert object_store.list_keys(f"knowledgebases/{kb_id}/") == []
    deletion_events = [
        event for event in event_bus.published_events
        if isinstance(event, KnowledgeBaseDeletedEvent)
    ]
    assert deletion_events[-1].knowledge_base_id == kb_id
    assert deletion_events[-1].cleanup_pending is False


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
    detail = client.get(f"/knowledgebases/{kb_id}")
    assert detail.status_code == 200
    assert detail.json()["document_count"] == 1


def test_register_documents_does_not_start_workflow_when_receipt_not_enqueued(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness

    class SuppressedIngestionService:
        def register_documents(
            self,
            knowledge_base_id: str,
            submissions: list[DocumentSubmission],
            *,
            correlation_id: str | None = None,
        ) -> list[DocumentReceipt]:
            del submissions, correlation_id
            return [
                DocumentReceipt(
                    knowledge_base_id=knowledge_base_id,
                    source_document_id="doc-suppressed",
                    filename="claims.json",
                    status=IngestionStatus.PENDING,
                    storage_key="knowledgebases/kb/documents/doc-suppressed/source",
                    enqueued=False,
                )
            ]

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_ingestion_service] = lambda: SuppressedIngestionService()
    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("claims.json", b'{"claim_id": "42"}', "application/json"))],
    )

    assert response.status_code == 202
    assert response.json()["documents"][0]["enqueued"] is False
    run_store = getattr(app.state, "workflow_run_store", None)
    assert run_store is None or run_store.list_runs().items == []


def test_register_documents_preserves_existing_replacement_when_registration_fails(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, object_store, repository = harness
    graph_service = _RecordingReplacementGraphService()
    vector_service = _RecordingReplacementVectorService()

    class FailingIngestionService:
        def register_documents(
            self,
            knowledge_base_id: str,
            submissions: list[DocumentSubmission],
            *,
            correlation_id: str | None = None,
        ) -> list[DocumentReceipt]:
            del knowledge_base_id, submissions, correlation_id
            raise RuntimeError("publish failed")

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_ingestion_service] = lambda: FailingIngestionService()

    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]
    content = b'{"claim_id": "42"}'
    content_hash = hashlib.sha256(content).hexdigest()
    old_document_id = "old-doc"
    old_source_key = f"knowledgebases/{kb_id}/documents/{old_document_id}/source"
    old_artifact_key = f"knowledgebases/{kb_id}/documents/{old_document_id}/artifact.json"
    repository.add_document(
        DocumentRecord(
            id=old_document_id,
            knowledge_base_id=kb_id,
            filename="claims.json",
            content_type="application/json",
            size_bytes=len(content),
            status=IngestionStatus.PENDING.value,
            storage_key=old_source_key,
            content_hash=content_hash,
        )
    )
    object_store.put_bytes(old_source_key, content, media_type="application/json")
    object_store.put_bytes(old_artifact_key, b"{}", media_type="application/json")
    graph_service.source_documents.add((kb_id, old_document_id))
    vector_service.source_documents.add((kb_id, old_document_id))

    with pytest.raises(RuntimeError, match="publish failed"):
        client.post(
            f"/knowledgebases/{kb_id}/documents",
            files=[("files", ("claims.json", content, "application/json"))],
        )

    assert repository.get_document(kb_id, old_document_id) is not None
    assert object_store.exists(old_source_key)
    assert object_store.exists(old_artifact_key)
    assert graph_service.source_documents == {(kb_id, old_document_id)}
    assert vector_service.source_documents == {(kb_id, old_document_id)}
    assert graph_service.deleted_source_documents == []
    assert vector_service.deleted_source_documents == []


def test_register_documents_cleans_replacement_after_successful_enqueue(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, object_store, repository = harness
    graph_service = _RecordingReplacementGraphService()
    vector_service = _RecordingReplacementVectorService()

    class SuccessfulIngestionService:
        def __init__(self, *, source_document_id: str, storage_key: str) -> None:
            self._source_document_id = source_document_id
            self._storage_key = storage_key

        def register_documents(
            self,
            knowledge_base_id: str,
            submissions: list[DocumentSubmission],
            *,
            correlation_id: str | None = None,
        ) -> list[DocumentReceipt]:
            del submissions, correlation_id
            return [
                DocumentReceipt(
                    knowledge_base_id=knowledge_base_id,
                    source_document_id=self._source_document_id,
                    filename="claims.json",
                    status=IngestionStatus.PENDING,
                    storage_key=self._storage_key,
                    enqueued=True,
                )
            ]

    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]
    content = b'{"claim_id": "42"}'
    content_hash = hashlib.sha256(content).hexdigest()
    old_document_id = "old-doc"
    old_source_key = f"knowledgebases/{kb_id}/documents/{old_document_id}/source"
    old_artifact_key = f"knowledgebases/{kb_id}/documents/{old_document_id}/artifact.json"
    repository.add_document(
        DocumentRecord(
            id=old_document_id,
            knowledge_base_id=kb_id,
            filename="old-name.json",
            content_type="application/json",
            size_bytes=len(content),
            status=IngestionStatus.PENDING.value,
            storage_key=old_source_key,
            content_hash=content_hash,
        )
    )
    object_store.put_bytes(old_source_key, content, media_type="application/json")
    object_store.put_bytes(old_artifact_key, b"{}", media_type="application/json")
    graph_service.source_documents.add((kb_id, old_document_id))
    vector_service.source_documents.add((kb_id, old_document_id))

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_ingestion_service] = lambda: SuccessfulIngestionService(
        source_document_id=old_document_id,
        storage_key=old_source_key,
    )

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("claims.json", content, "application/json"))],
    )

    assert response.status_code == 202
    receipt = response.json()["documents"][0]
    assert receipt["source_document_id"] == old_document_id
    assert receipt["replaced_document_id"] == old_document_id
    assert receipt["enqueued"] is True
    updated_document = repository.get_document(kb_id, old_document_id)
    assert updated_document is not None
    assert updated_document.filename == "claims.json"
    assert object_store.exists(old_source_key)
    assert not object_store.exists(old_artifact_key)
    assert graph_service.deleted_source_documents == [(kb_id, old_document_id)]
    assert vector_service.deleted_source_documents == [(kb_id, old_document_id)]
    assert graph_service.source_documents == set()
    assert vector_service.source_documents == set()


def test_register_documents_cleanup_failure_returns_500_and_preserves_new_source(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, object_store, repository = harness
    vector_service = _RecordingReplacementVectorService()

    class FailingGraphService(_RecordingReplacementGraphService):
        def delete_by_source_document(
            self,
            knowledge_base_id: str,
            source_document_id: str,
        ) -> GraphDeleteByProvenance:
            del knowledge_base_id, source_document_id
            raise RuntimeError("graph offline")

    class SuccessfulIngestionService:
        def __init__(self, *, source_document_id: str, storage_key: str) -> None:
            self._source_document_id = source_document_id
            self._storage_key = storage_key

        def register_documents(
            self,
            knowledge_base_id: str,
            submissions: list[DocumentSubmission],
            *,
            correlation_id: str | None = None,
        ) -> list[DocumentReceipt]:
            del submissions, correlation_id
            return [
                DocumentReceipt(
                    knowledge_base_id=knowledge_base_id,
                    source_document_id=self._source_document_id,
                    filename="claims.json",
                    status=IngestionStatus.PENDING,
                    storage_key=self._storage_key,
                    enqueued=True,
                )
            ]

    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]
    content = b'{"claim_id": "42"}'
    content_hash = hashlib.sha256(content).hexdigest()
    old_document_id = "old-doc"
    old_source_key = f"knowledgebases/{kb_id}/documents/{old_document_id}/source"
    repository.add_document(
        DocumentRecord(
            id=old_document_id,
            knowledge_base_id=kb_id,
            filename="old-name.json",
            content_type="application/json",
            size_bytes=len(content),
            status=IngestionStatus.PENDING.value,
            storage_key=old_source_key,
            content_hash=content_hash,
        )
    )
    object_store.put_bytes(old_source_key, content, media_type="application/json")

    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_graph_service] = lambda: FailingGraphService()
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_ingestion_service] = lambda: SuccessfulIngestionService(
        source_document_id=old_document_id,
        storage_key=old_source_key,
    )

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("claims.json", content, "application/json"))],
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        f"Failed to clean up replaced document '{old_document_id}'."
    )
    assert object_store.exists(old_source_key)
    assert repository.get_document(kb_id, old_document_id) is not None
    assert vector_service.deleted_source_documents == []


def test_register_documents_returns_404_for_missing_kb_without_side_effects(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, event_bus, object_store, _ = harness

    response = client.post(
        "/knowledgebases/missing/documents",
        files=[("files", ("claims.json", b'{"claim_id": "42"}', "application/json"))],
    )

    assert response.status_code == 404
    assert object_store.list_keys("knowledgebases/missing/") == []
    assert not any(
        isinstance(event, DocumentsUploadedEvent)
        for event in event_bus.published_events
    )


def test_register_documents_rejects_disallowed_content_type(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness
    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("payload.bin", b"abc", "application/octet-stream"))],
    )

    assert response.status_code == 415


def test_register_documents_rejects_oversized_file(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, _ = harness
    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("large.txt", b"x" * (2 * 1024 * 1024), "text/plain"))],
    )

    assert response.status_code == 413


def test_document_upload_reader_stops_when_size_limit_is_exceeded() -> None:
    class ChunkedUpload:
        filename = "large.txt"

        def __init__(self) -> None:
            self.chunks = [b"aa", b"aa", b"tail"]
            self.read_count = 0

        async def read(self, size: int = -1) -> bytes:
            assert size > 0
            self.read_count += 1
            return self.chunks.pop(0) if self.chunks else b""

    upload = ChunkedUpload()

    async def read_upload() -> None:
        await read_upload_file_with_limit(
            cast(UploadFile, upload),
            max_bytes=3,
            detail="too large",
        )

    with pytest.raises(HTTPException) as exc_info:
        anyio.run(read_upload)

    assert exc_info.value.status_code == 413
    assert upload.read_count == 2
    assert upload.chunks == [b"tail"]


def test_register_documents_sanitizes_filenames(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
) -> None:
    client, _, _, repository = harness
    created = client.post(
        "/knowledgebases", json={"name": "DocKb", "description": ""}
    )
    kb_id = created.json()["id"]

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("../../etc/passwd", b"hello", "text/plain"))],
    )

    assert response.status_code == 202
    documents, total = repository.list_documents(kb_id, limit=10, offset=0)
    assert total == 1
    assert documents[0].filename == "passwd"


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
    complete_inflight_workflows: Callable[[TestClient], None],
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
                    (
                        f"file-{index}.json",
                        f'{{"x": {index}}}'.encode("utf-8"),
                        "application/json",
                    ),
                )
            ],
        )
        # Each upload starts a workflow run (one per KB); finish it so the next
        # upload is not rejected by the busy guard.
        complete_inflight_workflows(client)

    response = client.get(
        f"/knowledgebases/{kb_id}/documents",
        params={"limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    summary = payload["items"][0]
    assert summary["knowledge_base_id"] == kb_id
    assert summary["filename"] == "file-0.json"
    assert summary["content_type"] == "application/json"
    assert summary["size_bytes"] == len(b'{"x": 0}')
    assert summary["status"]
    assert summary["created_at"]


def test_delete_document_removes_artifacts(
    harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
    ],
    complete_inflight_workflows: Callable[[TestClient], None],
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
    # The upload started a workflow run; finish it so the delete is not blocked
    # by the busy guard.
    complete_inflight_workflows(client)
    assert object_store.list_keys(
        f"knowledgebases/{kb_id}/documents/{document_id}/"
    )

    response = client.delete(
        f"/knowledgebases/{kb_id}/documents/{document_id}"
    )

    assert response.status_code == 204
    detail = client.get(f"/knowledgebases/{kb_id}")
    assert detail.status_code == 200
    assert detail.json()["document_count"] == 0
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


def test_kb_get_requires_viewer_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /knowledgebases requires viewer role."""
    import time
    from pathlib import Path

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", _skip_policy_audit)

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    domain = load_config(MEDICARE_YAML).model_copy(update={"auth": auth_cfg})
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-viewer",
            user_id="u-viewer",
            roles=["viewer"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # No cookie -> 401
        assert client.get("/knowledgebases").status_code == 401
        # Viewer cookie -> 200
        client.cookies.set("chiliai_session", "sid-viewer")
        assert client.get("/knowledgebases").status_code == 200


def test_kb_create_requires_analyst_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """POST /knowledgebases requires analyst (viewer gets 403, analyst succeeds)."""
    import time
    from pathlib import Path

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", _skip_policy_audit)

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    domain = load_config(MEDICARE_YAML).model_copy(update={"auth": auth_cfg})
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-viewer",
            user_id="u-viewer",
            roles=["viewer"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    store.save(
        SessionRecord(
            session_id="sid-analyst",
            user_id="u-analyst",
            roles=["analyst"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # Viewer cookie -> 403
        client.cookies.set("chiliai_session", "sid-viewer")
        assert client.post("/knowledgebases", json={"name": "test"}).status_code == 403
        # Analyst cookie -> 201
        client.cookies.set("chiliai_session", "sid-analyst")
        assert client.post("/knowledgebases", json={"name": "test"}).status_code == 201


def test_kb_delete_requires_admin_when_auth_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """DELETE /knowledgebases/{id} requires admin (analyst gets 403, admin succeeds)."""
    import time
    from pathlib import Path

    from api.app import create_app
    from api.dependencies import get_domain_config, get_session_store
    from api.middleware.session_store import InMemorySessionStore, SessionRecord
    from config.loader import load_config
    from config.schema import AuthConfig

    DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
    MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"

    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setattr("api.app.assert_complete", _skip_policy_audit)

    auth_cfg = AuthConfig(
        enabled=True,
        issuer_url="https://idp.example.com",
        audience="chili-api",
        jwks_uri="https://idp.example.com/jwks",
        client_id="chili-spa",
        client_secret_env_var="OIDC_CLIENT_SECRET",
        authorize_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/oauth/token",
        redirect_uri="https://app.example.com/auth/callback",
    )
    domain = load_config(MEDICARE_YAML).model_copy(update={"auth": auth_cfg})
    monkeypatch.setattr("api.app.load_config", lambda: domain)

    app = create_app()

    store = InMemorySessionStore()
    store.save(
        SessionRecord(
            session_id="sid-analyst",
            user_id="u-analyst",
            roles=["analyst"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    store.save(
        SessionRecord(
            session_id="sid-admin",
            user_id="u-admin",
            roles=["admin"],
            email=None,
            access_token="a",
            refresh_token="r",
            access_token_expires_at=time.time() + 3600,
            id_token="i",
            created_at=time.time(),
            ttl_seconds=3600,
        )
    )
    app.dependency_overrides[get_session_store] = lambda: store
    app.dependency_overrides[get_domain_config] = lambda: domain

    with TestClient(app) as client:
        # Use a non-existent KB id — the role check fires before the body,
        # so: analyst -> 403, admin -> 404 (role passes, KB absent)
        kb_id = "nonexistent-kb-id"

        # Analyst cookie -> 403 (role denied before 404 lookup)
        client.cookies.set("chiliai_session", "sid-analyst")
        assert client.delete(f"/knowledgebases/{kb_id}").status_code == 403

        # Admin cookie -> 404 (role passes; KB does not exist)
        client.cookies.set("chiliai_session", "sid-admin")
        assert client.delete(f"/knowledgebases/{kb_id}").status_code == 404


def _status_projection_harness() -> tuple[
    FastAPI, InMemoryKnowledgeBaseRepository, InMemorySourceDocumentStatusStore
]:
    app = create_app()
    repository = InMemoryKnowledgeBaseRepository()
    object_store = InMemoryObjectStore()
    status_store = InMemorySourceDocumentStatusStore()
    repository.create(
        KnowledgeBase(
            id="kb-proj",
            name="Projection KB",
            description="",
            status="active",
            created_at=utc_now(),
        )
    )
    for document_id in ("doc-failed", "doc-empty", "doc-clean"):
        repository.add_document(
            DocumentRecord(
                id=document_id,
                knowledge_base_id="kb-proj",
                filename=f"{document_id}.txt",
                content_type="text/plain",
                size_bytes=10,
                status="pending",
            )
        )
    status_store.apply(
        DocumentStatusTransition(
            knowledge_base_id="kb-proj",
            source_document_id="doc-failed",
            status=IngestionStatus.FAILED,
            error_message="parser exploded",
        )
    )
    status_store.apply(
        DocumentStatusTransition(
            knowledge_base_id="kb-proj",
            source_document_id="doc-empty",
            status=IngestionStatus.EXTRACTED_EMPTY,
            dropped_entity_count=4,
            dropped_relationship_count=1,
            sample_reasons=["entity cand-1: unknown type"],
        )
    )
    graph_service = _MetricsOnlyGraphService(
        GraphMetrics(entity_count=0, relationship_count=0, avg_degree=0.0)
    )
    app.dependency_overrides[get_knowledge_base_repository] = lambda: repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_domain_config] = _build_config
    app.dependency_overrides[get_document_status_store] = lambda: status_store
    return app, repository, status_store


def test_documents_endpoint_returns_durable_projection_fields() -> None:
    app, _, _ = _status_projection_harness()
    with TestClient(app) as client:
        response = client.get("/knowledgebases/kb-proj/documents")

    assert response.status_code == 200
    items = {item["id"]: item for item in response.json()["items"]}
    assert items["doc-failed"]["current_status"] == "failed"
    assert items["doc-failed"]["last_error"] == "parser exploded"
    assert items["doc-empty"]["current_status"] == "extracted_empty"
    assert items["doc-empty"]["dropped_entity_count"] == 4
    assert items["doc-empty"]["dropped_relationship_count"] == 1
    assert items["doc-empty"]["drop_sample_reasons"] == [
        "entity cand-1: unknown type"
    ]
    assert items["doc-clean"]["current_status"] is None
    assert items["doc-clean"]["last_error"] is None
    assert items["doc-clean"]["dropped_entity_count"] == 0


def test_documents_endpoint_filters_by_durable_status() -> None:
    app, _, _ = _status_projection_harness()
    with TestClient(app) as client:
        response = client.get("/knowledgebases/kb-proj/documents?status=failed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [item["id"] for item in payload["items"]] == ["doc-failed"]
    assert payload["items"][0]["current_status"] == "failed"


def test_documents_endpoint_rejects_unknown_status_filter() -> None:
    app, _, _ = _status_projection_harness()
    with TestClient(app) as client:
        response = client.get("/knowledgebases/kb-proj/documents?status=bogus")

    assert response.status_code == 422


def test_deleting_document_purges_its_status_row_from_filtered_total() -> None:
    """Regression: an orphaned status row must not inflate `total` past `items`.

    Before the fix, deleting a document left its row in the status store, so
    a status-filtered list still counted it in `total` while dropping it from
    `items` (e.g. `total: 1, items: []`).
    """
    app, _, status_store = _status_projection_harness()
    with TestClient(app) as client:
        delete_response = client.delete(
            "/knowledgebases/kb-proj/documents/doc-failed"
        )
        assert delete_response.status_code == 204

        response = client.get("/knowledgebases/kb-proj/documents?status=failed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["items"] == []
    assert (
        status_store.get_many(
            knowledge_base_id="kb-proj", source_document_ids=["doc-failed"]
        )
        == {}
    )
