"""KB DELETE cascade orchestration: full success, partial failure, busy guard.

These tests exercise the rewritten DELETE /knowledgebases/{id} endpoint using
lightweight in-memory adapters wired directly into the FastAPI app — no
workers, no external services.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import cast
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState
from agent.workflow_tracking import WorkflowEventTracker
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from api.app import create_app
from analytics.peerstats.adapters.in_memory import InMemoryDerivedRiskSignalWriter
from analytics.peerstats.models import DerivedRiskSignal
from api.dependencies import (
    get_derived_signal_store,
    get_risk_history_writer,
    get_event_bus,
    get_domain_config,
    get_graph_service,
    get_knowledge_base_repository,
    get_object_store,
    get_raw_record_store,
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
from events.types import KnowledgeBaseDeletedEvent
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from records.adapters.in_memory import InMemoryRawRecordStore
from records.models import RawRecord, content_hash_for
from shared.types import Entity
from shared.utils import generate_id, utc_now
from storage.adapters.in_memory import InMemoryObjectStore
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.models import VectorRecord
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
            allowed_content_types=["text/plain"],
        ),
        alerts=AlertsConfig(thresholds={}),
    )


def _seed_raw_record(store: InMemoryRawRecordStore, knowledge_base_id: str) -> None:
    payload: dict[str, object] = {"value": "seed"}
    store.persist(
        [
            RawRecord(
                knowledge_base_id=knowledge_base_id,
                record_type="test_record",
                record_id="rec-1",
                payload=payload,
                source_type="file_upload",
                correlation_id=generate_id(),
                content_hash=content_hash_for(payload),
                ingested_at=utc_now(),
            )
        ]
    )


def _seed_vector_record(store: InMemoryVectorStore, knowledge_base_id: str) -> None:
    store.upsert_records(
        knowledge_base_id,
        [
            VectorRecord(
                id=generate_id(),
                knowledge_base_id=knowledge_base_id,
                content_id=generate_id(),
                embedding=[0.1, 0.2, 0.3],
            )
        ],
    )


def _seed_graph_entity(
    repository: InMemoryGraphRepository, knowledge_base_id: str
) -> None:
    repository.upsert_entities(
        knowledge_base_id,
        [Entity(id=generate_id(), type="test", properties={})],
    )


# ---------------------------------------------------------------------------
# Shared harness fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def cascade_harness() -> Iterator[
    tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        WorkflowEventTracker,
    ]
]:
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

    app.dependency_overrides[get_domain_config] = _build_config
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_object_store] = lambda: object_store
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_vectorstore_service] = lambda: vector_service
    app.dependency_overrides[get_vector_service] = lambda: vector_service
    app.dependency_overrides[get_raw_record_store] = lambda: raw_record_store
    app.dependency_overrides[get_workflow_tracker] = lambda: workflow_tracker

    with TestClient(app) as client:
        yield (
            client,
            event_bus,
            object_store,
            kb_repository,
            graph_repository,
            vector_store,
            raw_record_store,
            workflow_tracker,
        )

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_delete_kb_cascades_through_all_stores(
    cascade_harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        WorkflowEventTracker,
    ],
) -> None:
    """Full success: all four cascade steps complete; 204 returned; KB metadata gone."""
    (
        client,
        event_bus,
        object_store,
        kb_repository,
        graph_repository,
        vector_store,
        raw_record_store,
        _,
    ) = cascade_harness

    # Create a KB through the API so the repository is aware of it.
    created = client.post("/knowledgebases", json={"name": "cascade-test", "description": ""})
    assert created.status_code == 201
    kb_id: str = created.json()["id"]

    # Seed state in each store.
    _seed_graph_entity(graph_repository, kb_id)
    _seed_vector_record(vector_store, kb_id)
    _seed_raw_record(raw_record_store, kb_id)
    object_store.put_bytes(
        f"knowledgebases/{kb_id}/test.json", b"{}", media_type="application/json"
    )

    # Verify pre-conditions.
    assert graph_repository.count_entities(kb_id) > 0
    assert vector_store.count_records(kb_id) > 0
    assert raw_record_store.count_for_kb(kb_id) > 0

    response = client.delete(f"/knowledgebases/{kb_id}")

    assert response.status_code == 204
    assert response.content == b""

    # All stores cleared.
    assert graph_repository.count_entities(kb_id) == 0
    assert vector_store.count_records(kb_id) == 0
    assert raw_record_store.count_for_kb(kb_id) == 0
    assert object_store.list_keys(f"knowledgebases/{kb_id}/") == []

    # KB metadata removed (404 on subsequent GET).
    assert client.get(f"/knowledgebases/{kb_id}").status_code == 404

    # Deletion event published with cleanup_pending=False.
    deletion_events = [
        e for e in event_bus.published_events if isinstance(e, KnowledgeBaseDeletedEvent)
    ]
    assert len(deletion_events) == 1
    assert deletion_events[0].knowledge_base_id == kb_id
    assert deletion_events[0].cleanup_pending is False


def test_delete_kb_returns_207_on_partial_failure(
    cascade_harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        WorkflowEventTracker,
    ],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Partial failure: vector step bombs; 207 returned; KB flagged pending_cleanup."""
    (
        client,
        event_bus,
        _object_store,
        kb_repository,
        graph_repository,
        vector_store,
        raw_record_store,
        _,
    ) = cascade_harness

    created = client.post("/knowledgebases", json={"name": "partial-fail", "description": ""})
    assert created.status_code == 201
    kb_id: str = created.json()["id"]

    _seed_graph_entity(graph_repository, kb_id)
    _seed_vector_record(vector_store, kb_id)
    _seed_raw_record(raw_record_store, kb_id)

    # Make the vector store's delete_namespace raise.
    def boom(*args: object, **kwargs: object) -> int:
        raise RuntimeError("simulated vectorstore outage")

    monkeypatch.setattr(InMemoryVectorStore, "delete_namespace", boom)

    response = client.delete(f"/knowledgebases/{kb_id}")

    assert response.status_code == 207
    body = response.json()
    assert body["knowledge_base_id"] == kb_id
    assert body["pending_cleanup"] is True
    statuses = {step["step"]: step["status"] for step in body["steps"]}
    assert statuses["graph"] == "succeeded"
    assert statuses["vector"] == "failed"
    assert "error" in next(s for s in body["steps"] if s["step"] == "vector")

    # KB still exists (not deleted) and is flagged pending_cleanup.
    kb_meta = kb_repository.get(kb_id)
    assert kb_meta is not None
    assert kb_meta.pending_cleanup is True

    # Deletion event published with cleanup_pending=True.
    deletion_events = [
        e for e in event_bus.published_events if isinstance(e, KnowledgeBaseDeletedEvent)
    ]
    assert len(deletion_events) == 1
    assert deletion_events[0].cleanup_pending is True


def test_delete_kb_returns_409_when_workflow_busy(
    cascade_harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        WorkflowEventTracker,
    ],
) -> None:
    """Busy guard: returns 409 when an active workflow run is in flight."""
    (
        client,
        event_bus,
        _object_store,
        _kb_repository,
        _graph_repository,
        _vector_store,
        _raw_record_store,
        workflow_tracker,
    ) = cascade_harness

    created = client.post("/knowledgebases", json={"name": "busy-kb", "description": ""})
    assert created.status_code == 201
    kb_id: str = created.json()["id"]

    # Seed a RUNNING workflow run for this KB so is_busy returns True.
    workflow_tracker._run_store.save_run(
        WorkflowRun(
            workflow_id=generate_id(),
            knowledge_base_id=kb_id,
            trigger_event_type="documents.uploaded",
            status=WorkflowRunStatus.RUNNING,
            steps=[WorkflowStepState(step_name="parse")],
        )
    )

    response = client.delete(f"/knowledgebases/{kb_id}")

    assert response.status_code == 409
    # No deletion event published.
    assert not any(
        isinstance(e, KnowledgeBaseDeletedEvent) for e in event_bus.published_events
    )


def test_delete_kb_returns_404_when_missing(
    cascade_harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        WorkflowEventTracker,
    ],
) -> None:
    """Missing KB returns 404 immediately; no event published."""
    client, event_bus, *_ = cascade_harness

    response = client.delete("/knowledgebases/nonexistent-id")

    assert response.status_code == 404
    assert not any(
        isinstance(e, KnowledgeBaseDeletedEvent) for e in event_bus.published_events
    )


def _seed_derived_signal(
    store: InMemoryDerivedRiskSignalWriter, knowledge_base_id: str
) -> None:
    store.write_signals(
        [
            DerivedRiskSignal(
                knowledge_base_id=knowledge_base_id,
                entity_id="provider:1",
                entity_type="provider",
                metric_name="weekly_billing",
                interval_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
                peer_group_key="provider",
                aggregate_value=10.0,
                peer_mean=5.0,
                peer_std=2.0,
                z_score=2.5,
                signal_value=0.5,
                weight=1.0,
                rationale="r",
                correlation_id="c",
            )
        ]
    )


def test_delete_kb_purges_derived_signals(
    cascade_harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        WorkflowEventTracker,
    ],
) -> None:
    """The KB-delete cascade purges entity_derived_signals (peerstats)."""
    client, *_ = cascade_harness
    derived_signal_store = InMemoryDerivedRiskSignalWriter()
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_derived_signal_store] = (
        lambda: derived_signal_store
    )

    created = client.post(
        "/knowledgebases", json={"name": "derived-cleanup", "description": ""}
    )
    assert created.status_code == 201
    kb_id: str = created.json()["id"]

    _seed_derived_signal(derived_signal_store, kb_id)
    assert (
        derived_signal_store.latest_signals(
            knowledge_base_id=kb_id, entity_id="provider:1"
        )
        != []
    )

    response = client.delete(f"/knowledgebases/{kb_id}")
    assert response.status_code == 204
    assert (
        derived_signal_store.latest_signals(
            knowledge_base_id=kb_id, entity_id="provider:1"
        )
        == []
    )


def test_delete_kb_207_when_a_durable_store_step_fails(
    cascade_harness: tuple[
        TestClient,
        InMemoryEventBus,
        InMemoryObjectStore,
        InMemoryKnowledgeBaseRepository,
        InMemoryGraphRepository,
        InMemoryVectorStore,
        InMemoryRawRecordStore,
        WorkflowEventTracker,
    ],
) -> None:
    """A failure in one of the per-KB durable stores surfaces in the 207 body."""
    client, *_ = cascade_harness
    failing = MagicMock()
    failing.delete_by_kb.side_effect = RuntimeError("risk-history outage")
    app = cast(FastAPI, client.app)
    app.dependency_overrides[get_risk_history_writer] = lambda: failing

    created = client.post(
        "/knowledgebases", json={"name": "risk-fail", "description": ""}
    )
    assert created.status_code == 201
    kb_id: str = created.json()["id"]

    response = client.delete(f"/knowledgebases/{kb_id}")
    assert response.status_code == 207
    statuses = {step["step"]: step["status"] for step in response.json()["steps"]}
    assert statuses["risk_history"] == "failed"
    # Other steps still ran (best-effort cascade).
    assert statuses["graph"] == "succeeded"
    assert statuses["conversations"] == "succeeded"
    failing.delete_by_kb.assert_called_once_with(kb_id)
