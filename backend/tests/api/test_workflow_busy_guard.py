"""POST/DELETE endpoints that mutate KB state must refuse when a workflow is busy."""

from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from agent.workflow_tracking import WorkflowEventTracker
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository  # noqa: F401 (also used in pending_cleanup tests)
from api.app import create_app
from api.dependencies import (
    get_domain_config,
    get_event_bus,
    get_graph_service,
    get_knowledge_base_repository,
    get_object_store,
    get_raw_record_store,
    get_records_service,
    get_vector_service,
    get_vectorstore_service,
    get_workflow_tracker,
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
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from records.adapters.in_memory import InMemoryRawRecordStore
from shared.utils import generate_id
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
            max_file_size_mb=1,
            allowed_content_types=["application/json", "text/csv", "text/plain"],
        ),
        alerts=AlertsConfig(thresholds={}),
    )


# ---------------------------------------------------------------------------
# Shared harness fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def busy_guard_harness() -> Iterator[tuple[TestClient, WorkflowEventTracker]]:
    app = create_app()

    event_bus = InMemoryEventBus()
    object_store = InMemoryObjectStore()
    kb_repository = InMemoryKnowledgeBaseRepository()
    graph_repository = InMemoryGraphRepository()
    raw_record_store = InMemoryRawRecordStore()
    vector_store = InMemoryVectorStore()
    workflow_run_store = InMemoryWorkflowRunStore()
    workflow_tracker = WorkflowEventTracker(workflow_run_store)

    graph_service = create_graph_service(
        graph_repository,
        object_store=object_store,
        event_bus=event_bus,
    )
    vector_service = create_vector_service(
        vector_store,
        event_bus=event_bus,
        object_store=object_store,
    )

    # Stub records service that does nothing (busy guard fires before service is reached)
    class _NullRecordsService:
        def register_records(
            self, knowledge_base_id: str, submission: object
        ) -> object:
            raise AssertionError("should not reach records service when KB is busy")

    app.dependency_overrides[get_domain_config] = _build_config
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vectorstore_service] = lambda: vector_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_raw_record_store] = lambda: raw_record_store
    app.dependency_overrides[get_workflow_tracker] = lambda: workflow_tracker
    app.dependency_overrides[get_records_service] = lambda: _NullRecordsService()

    with TestClient(app) as client:
        yield client, workflow_tracker

    app.dependency_overrides.clear()


def _force_busy(workflow_tracker: WorkflowEventTracker, knowledge_base_id: str) -> None:
    """Insert a RUNNING workflow run so is_busy returns True."""
    workflow_tracker._run_store.save_run(
        WorkflowRun(
            workflow_id=generate_id(),
            knowledge_base_id=knowledge_base_id,
            trigger_event_type="documents.uploaded",
            status=WorkflowRunStatus.RUNNING,
            steps=[WorkflowStepState(step_name="parse")],
        )
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_document_upload_returns_409_when_busy(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """POST /knowledgebases/{id}/documents returns 409 when a workflow is in flight."""
    client, workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "busy-doc", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    _force_busy(workflow_tracker, kb_id)

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", BytesIO(b"{}"), "application/json"))],
    )
    assert response.status_code == 409


def test_records_upload_returns_409_when_busy(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """POST /records/{kb_id}/files returns 409 when a workflow is in flight."""
    client, workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "busy-records", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    _force_busy(workflow_tracker, kb_id)

    response = client.post(
        f"/records/{kb_id}/files",
        files={"file": ("tiny.csv", BytesIO(b"a\n1\n"), "text/csv")},
        data={"feed": "carrier_claims_a"},
    )
    assert response.status_code == 409


def test_document_delete_returns_409_when_busy(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """DELETE /knowledgebases/{id}/documents/{doc_id} returns 409 when busy."""
    client, workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "busy-del-doc", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    # Upload a document first so there is a valid doc_id to delete
    upload = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", BytesIO(b"{}"), "application/json"))],
    )
    assert upload.status_code == 202
    doc_id: str = upload.json()["documents"][0]["source_document_id"]

    _force_busy(workflow_tracker, kb_id)

    response = client.delete(f"/knowledgebases/{kb_id}/documents/{doc_id}")
    assert response.status_code == 409


def test_document_upload_succeeds_when_idle(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """POST /knowledgebases/{id}/documents succeeds (202) when no workflow is running."""
    client, _workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "idle-doc", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", BytesIO(b"{}"), "application/json"))],
    )
    assert response.status_code == 202


# ---------------------------------------------------------------------------
# pending_cleanup guard tests
# ---------------------------------------------------------------------------


def _force_pending_cleanup(
    kb_repository: InMemoryKnowledgeBaseRepository, knowledge_base_id: str
) -> None:
    """Mark the KB as pending cleanup so the guard should fire."""
    kb_repository.mark_pending_cleanup(knowledge_base_id)


def test_document_upload_returns_409_when_pending_cleanup(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """POST /documents returns 409 when KB is in pending_cleanup state."""
    client, _workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "cleanup-doc", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    # Force pending_cleanup — we need direct repo access; use the harness's kb_repository
    # via a fresh InMemoryKnowledgeBaseRepository that we injected in the fixture.
    # The fixture exposes kb_repository, so access it via the override.
    from api.dependencies import get_knowledge_base_repository
    from api.app import create_app as _unused_import  # noqa: F401

    # Access the kb_repository used by the test client.
    # The fixture binds it via dependency override and we stored the reference.
    # We need to look up the correct kb_repository from the override.
    # Since the fixture stores the kb_repository as a local var, we use the same
    # approach as _force_busy: access internal state.
    # Get the overridden kb_repository from the app's dependency overrides.
    from fastapi.testclient import TestClient as _TC
    assert isinstance(client, _TC)
    app = cast(FastAPI, client.app)
    override_fn = app.dependency_overrides.get(get_knowledge_base_repository)
    assert override_fn is not None, "kb_repository override not found"
    kb_repo = override_fn()
    assert isinstance(kb_repo, InMemoryKnowledgeBaseRepository)
    _force_pending_cleanup(kb_repo, kb_id)

    response = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", BytesIO(b"{}"), "application/json"))],
    )
    assert response.status_code == 409
    assert "pending cleanup" in response.json()["detail"]


def test_records_upload_returns_409_when_pending_cleanup(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """POST /records/{kb_id}/files returns 409 when KB is in pending_cleanup state."""
    client, _workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "cleanup-records", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    from api.dependencies import get_knowledge_base_repository
    app = cast(FastAPI, client.app)
    override_fn = app.dependency_overrides.get(get_knowledge_base_repository)
    assert override_fn is not None
    kb_repo = override_fn()
    assert isinstance(kb_repo, InMemoryKnowledgeBaseRepository)
    _force_pending_cleanup(kb_repo, kb_id)

    response = client.post(
        f"/records/{kb_id}/files",
        files={"file": ("tiny.csv", BytesIO(b"a\n1\n"), "text/csv")},
        data={"feed": "carrier_claims_a"},
    )
    assert response.status_code == 409
    assert "pending cleanup" in response.json()["detail"]


def test_document_delete_returns_409_when_pending_cleanup(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """DELETE /documents/{doc_id} returns 409 when KB is in pending_cleanup state."""
    client, _workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "cleanup-del", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    upload = client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", BytesIO(b"{}"), "application/json"))],
    )
    assert upload.status_code == 202
    doc_id: str = upload.json()["documents"][0]["source_document_id"]

    from api.dependencies import get_knowledge_base_repository
    app = cast(FastAPI, client.app)
    override_fn = app.dependency_overrides.get(get_knowledge_base_repository)
    assert override_fn is not None
    kb_repo = override_fn()
    assert isinstance(kb_repo, InMemoryKnowledgeBaseRepository)
    _force_pending_cleanup(kb_repo, kb_id)

    response = client.delete(f"/knowledgebases/{kb_id}/documents/{doc_id}")
    assert response.status_code == 409
    assert "pending cleanup" in response.json()["detail"]


def test_kb_delete_is_reentrant_when_pending_cleanup(
    busy_guard_harness: tuple[TestClient, WorkflowEventTracker],
) -> None:
    """DELETE /knowledgebases/{id} is re-entrant when the KB is in pending_cleanup.

    Unlike upload / document-delete (which refuse with 409 while a KB is in
    ``pending_cleanup``), KB delete is the *recovery path*: re-issuing it retries
    the cascade cleanup. With healthy backends the retry completes and removes the
    KB (204). The ``pending_cleanup -> 409`` guard was intentionally removed from
    this route in 9e0de91 ("streamline records ingest and kb cleanup") so stuck
    KBs are never undeletable; there is no separate cleanup-retry endpoint.
    """
    client, _workflow_tracker = busy_guard_harness

    create = client.post("/knowledgebases", json={"name": "cleanup-kb-del", "description": ""})
    assert create.status_code == 201
    kb_id: str = create.json()["id"]

    from api.dependencies import get_knowledge_base_repository
    app = cast(FastAPI, client.app)
    override_fn = app.dependency_overrides.get(get_knowledge_base_repository)
    assert override_fn is not None
    kb_repo = override_fn()
    assert isinstance(kb_repo, InMemoryKnowledgeBaseRepository)
    _force_pending_cleanup(kb_repo, kb_id)

    response = client.delete(f"/knowledgebases/{kb_id}")

    # Re-running the delete retries cleanup; healthy in-memory backends succeed,
    # so the KB is fully removed rather than blocked.
    assert response.status_code == 204
    assert kb_repo.get(kb_id) is None
