"""Tests for service-backed Phase 5 routes and persisted write flows."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api._alert_store import AlertProjectionRecord, InMemoryAlertProjectionRepository
from api.app import create_app
from api.dependencies import get_alert_repository
from shared.types import Alert
from shared.utils import utc_now


def _client_with_alert_projection() -> TestClient:
    """Create a test client with deterministic alert projection records."""
    app = create_app()
    repository = InMemoryAlertProjectionRepository()
    repository.upsert(
        AlertProjectionRecord(
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
    created = client.post(
        "/cases",
        json={
            "title": "New escalation case",
            "priority": "medium",
            "assignee": "J. Chen",
            "alert_ids": [alert_id],
        },
    )

    assert created.status_code == 200
    case_id = created.json()["case"]["id"]

    updated = client.patch(f"/cases/{case_id}", json={"status": "in_review", "priority": "high"})
    assert updated.status_code == 200
    assert updated.json()["case"]["status"] == "in_review"

    feedback = client.post(
        f"/cases/{case_id}/feedback",
        json={
            "label": "suspicious",
            "evidence_adequacy": "high",
            "missing_evidence": [],
            "notes": "Evidence is sufficient for escalation.",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["feedback_history"][-1]["label"] == "suspicious"


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


def test_graph_and_analytics_routes_are_service_backed() -> None:
    client = _client_with_alert_projection()

    alerts = client.get("/alerts").json()["items"]
    entity_id = alerts[0]["entity_id"]
    evidence_id = alerts[0]["evidence_pack_id"]

    graph_detail = client.get(f"/graph/entities/{entity_id}")
    risk_score = client.get(f"/analytics/risk-scores/{entity_id}")
    timeseries = client.get(f"/analytics/timeseries/{entity_id}")
    evidence = client.get(f"/evidence-packs/{evidence_id}")

    assert graph_detail.status_code == 200
    assert graph_detail.json()["entity"]["id"] == entity_id
    assert risk_score.status_code == 200
    assert risk_score.json()["overall_score"] > 0.0
    assert timeseries.status_code == 200
    assert any(point["is_anomaly"] for point in timeseries.json()["points"])
    assert evidence.status_code == 200
    assert evidence.json()["alert_id"] == alerts[0]["id"]