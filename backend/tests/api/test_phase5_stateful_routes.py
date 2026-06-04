"""Tests for service-backed Phase 5 routes and persisted write flows."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api._alert_store import AlertProjectionRecord, InMemoryAlertProjectionRepository
from api.app import create_app
from api.dependencies import (
    get_alert_repository,
    get_graph_service,
    get_knowledge_base_repository,
)
from events.adapters.in_memory import InMemoryEventBus
from graph import InMemoryGraphRepository, create_graph_service
from graph.protocols import GraphServiceProtocol
from knowledgebases import InMemoryKnowledgeBaseRepository
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import Alert, Entity, KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


def _client_with_alert_projection() -> TestClient:
    """Create a test client with deterministic alert projection records."""
    app = create_app()
    repository = InMemoryAlertProjectionRepository()
    repository.upsert(
        AlertProjectionRecord(
            knowledge_base_id="kb-1",
            alert=Alert(
                id="alert-001",
                entity_type="provider",
                entity_id="provider-204",
                severity="critical",
                title="Outlier billing concentration",
                reasoning="Provider activity is materially above peers.",
                evidence_pack_id="evidence-001",
                created_at=utc_now(),
            ),
            entity_label="Redwood DME Group",
            confidence=0.96,
            tags=["billing"],
        )
    )
    app.dependency_overrides[get_alert_repository] = lambda: repository
    return TestClient(app)


def test_alert_acknowledgement_changes_status() -> None:
    client = _client_with_alert_projection()

    alerts = client.get("/alerts").json()["items"]
    alert_id = alerts[0]["id"]

    response = client.post(f"/alerts/{alert_id}/acknowledge")

    assert response.status_code == 200
    updated = client.get(f"/alerts/{alert_id}").json()
    assert updated["alert"]["status"] == "acknowledged"


def test_create_and_update_case_and_append_feedback() -> None:
    client = _client_with_alert_projection()

    alert_id = client.get("/alerts").json()["items"][0]["id"]
    kb = {"knowledge_base_id": "kb-1"}
    created = client.post(
        "/cases",
        params=kb,
        json={
            "title": "New escalation case",
            "priority": "medium",
            "assignee": "J. Chen",
            "alert_ids": [alert_id],
        },
    )

    assert created.status_code == 200
    case_id = created.json()["case"]["id"]
    assert created.json()["case"]["knowledge_base_id"] == "kb-1"

    updated = client.patch(
        f"/cases/{case_id}", params=kb, json={"status": "in_review", "priority": "high"}
    )
    assert updated.status_code == 200
    assert updated.json()["case"]["status"] == "in_review"

    feedback = client.post(
        f"/cases/{case_id}/feedback",
        params=kb,
        json={
            "label": "suspicious",
            "evidence_adequacy": "high",
            "missing_evidence": [],
            "notes": "Evidence is sufficient for escalation.",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["feedback_history"][-1]["label"] == "suspicious"


def test_promote_alert_to_case_captures_origin_and_evidence() -> None:
    client = _client_with_alert_projection()

    promoted = client.post(
        "/cases/promote",
        params={"knowledge_base_id": "kb-1"},
        json={"alert_id": "alert-001", "notes": "Escalate for review"},
    )

    assert promoted.status_code == 200
    case = promoted.json()["case"]
    assert case["originating_alert_id"] == "alert-001"
    assert case["evidence_pack_id"] == "evidence-001"
    assert case["alert_ids"] == ["alert-001"]
    assert case["priority"] == "critical"  # mapped from alert severity
    assert case["status"] == "open"
    assert case["knowledge_base_id"] == "kb-1"
    # Timeline snapshot captured from the originating alert.
    assert promoted.json()["entity_timeline"][0]["label"] == "alert_raised"

    # The promoted case is now listed under its KB.
    listed = client.get("/cases", params={"knowledge_base_id": "kb-1"}).json()
    assert [item["id"] for item in listed["items"]] == [case["id"]]


def test_promote_unknown_alert_returns_404() -> None:
    client = _client_with_alert_projection()

    response = client.post(
        "/cases/promote",
        params={"knowledge_base_id": "kb-1"},
        json={"alert_id": "missing-alert"},
    )

    assert response.status_code == 404


def test_create_conversation_and_add_message() -> None:
    client = TestClient(create_app())

    created = client.post(
        "/chat/conversations",
        json={"knowledge_base_id": "kb-1", "title": "Fresh triage thread"},
    )

    assert created.status_code == 200
    conversation_id = created.json()["id"]

    updated = client.post(
        f"/chat/conversations/{conversation_id}/messages",
        json={"content": "Why is provider-204 risky?", "include_graph_context": True, "filters": {}},
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert len(payload["messages"]) == 2
    assert payload["messages"][-1]["role"] == "assistant"


def _seeded_graph_service(entity_id: str) -> GraphServiceProtocol:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [Entity(id=entity_id, type="provider", properties={"display_name": "Seeded"})],
    )
    return create_graph_service(
        repository,
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )


def _seeded_kb_repository() -> KnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id="kb-1",
            name="KB",
            description="Seeded",
            entity_count=1,
            status="ready",
            created_at=utc_now(),
        )
    )
    return repository


def test_graph_and_analytics_routes_are_service_backed() -> None:
    app = create_app()
    repository = InMemoryAlertProjectionRepository()
    repository.upsert(
        AlertProjectionRecord(
            knowledge_base_id="kb-1",
            alert=Alert(
                id="alert-001",
                entity_type="provider",
                entity_id="provider-204",
                severity="critical",
                title="Outlier billing concentration",
                reasoning="Provider activity is materially above peers.",
                evidence_pack_id="evidence-001",
                created_at=utc_now(),
            ),
            entity_label="Redwood DME Group",
            confidence=0.96,
            tags=["billing"],
        )
    )
    app.dependency_overrides[get_alert_repository] = lambda: repository
    graph_service = _seeded_graph_service("provider-204")
    kb_repository = _seeded_kb_repository()
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    client = TestClient(app)

    alerts = client.get("/alerts").json()["items"]
    entity_id = alerts[0]["entity_id"]
    evidence_id = alerts[0]["evidence_pack_id"]

    graph_detail = client.get(f"/graph/entities/{entity_id}")
    risk_score = client.get(f"/analytics/risk-scores/{entity_id}", params={"kb_id": "kb-1"})
    timeseries = client.get(f"/analytics/timeseries/{entity_id}", params={"kb_id": "kb-1"})
    evidence = client.get(
        f"/evidence-packs/{evidence_id}", params={"knowledge_base_id": "kb-1"}
    )

    assert graph_detail.status_code == 200
    assert graph_detail.json()["entity"]["id"] == entity_id
    assert risk_score.status_code == 200
    assert risk_score.json()["overall_score"] > 0.0
    assert timeseries.status_code == 200
    assert any(point["is_anomaly"] for point in timeseries.json()["points"])
    # Evidence packs are now served from the persisted repository (BL-005); the
    # seeded alert's pack is not persisted, so the endpoint reports 404 rather
    # than returning a seeded read model.
    assert evidence.status_code == 404
