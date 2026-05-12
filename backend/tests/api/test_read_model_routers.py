"""Tests for Phase 4 scaffold read-model routers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState, WorkflowStepStatus
from agent.service import create_agent_service
from api._alert_store import AlertProjectionRecord, InMemoryAlertProjectionRepository
from api.app import create_app
from api.contracts import PolicyCitation
from api.dependencies import get_agent_service, get_alert_repository
from events.adapters.in_memory import InMemoryEventBus
from shared.types import Alert
from shared.utils import utc_now


def _seed_alert_repository() -> InMemoryAlertProjectionRepository:
    """Return a deterministic alert projection repository for API tests."""
    repository = InMemoryAlertProjectionRepository()
    created_at = utc_now()
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
                created_at=created_at,
            ),
            entity_label="Redwood DME Group",
            confidence=0.96,
            tags=["billing", "peer-deviation"],
            related_entity_ids=["provider-204", "claim-8821"],
            policy_citations=[
                PolicyCitation(
                    citation_id="policy-17",
                    title="CMS Billing Integrity Manual",
                    excerpt="Claims require documented medical necessity.",
                    source_document_id="doc-policy-17",
                )
            ],
        )
    )
    repository.upsert(
        AlertProjectionRecord(
            alert=Alert(
                id="alert-002",
                entity_type="provider",
                entity_id="provider-118",
                severity="high",
                title="Referral concentration anomaly",
                reasoning="Referral traffic is concentrated outside norms.",
                evidence_pack_id=None,
                created_at=created_at - timedelta(minutes=5),
            ),
            entity_label="North Harbor Imaging",
            confidence=0.84,
            tags=["network"],
        )
    )
    return repository


def _client_with_alerts() -> TestClient:
    """Create a test client whose /alerts route uses projection data."""
    app = create_app()
    repository = _seed_alert_repository()
    app.dependency_overrides[get_alert_repository] = lambda: repository
    return TestClient(app)


def _client_with_workflows() -> TestClient:
    """Create a test client whose /workflows route uses agent service data."""
    app = create_app()
    run_store = InMemoryWorkflowRunStore(
        runs=[
            WorkflowRun(
                workflow_id="workflow-ingestion-complete",
                knowledge_base_id="kb-1",
                trigger_event_type="documents.uploaded",
                status=WorkflowRunStatus.COMPLETED,
                steps=[
                    WorkflowStepState(
                        step_name="parse",
                        status=WorkflowStepStatus.COMPLETED,
                    )
                ],
                created_at=datetime(2026, 5, 8, 12, tzinfo=timezone.utc),
            ),
            WorkflowRun(
                workflow_id="workflow-analytics-running",
                knowledge_base_id="kb-1",
                trigger_event_type="analytics.risk_scored",
                status=WorkflowRunStatus.RUNNING,
                steps=[
                    WorkflowStepState(
                        step_name="risk_scoring",
                        status=WorkflowStepStatus.RUNNING,
                    )
                ],
                created_at=datetime(2026, 5, 8, 14, tzinfo=timezone.utc),
            ),
        ]
    )
    agent_service = create_agent_service(run_store, event_bus=InMemoryEventBus())
    app.dependency_overrides[get_agent_service] = lambda: agent_service
    return TestClient(app)


def test_get_alerts_returns_paginated_feed() -> None:
    client = _client_with_alerts()

    response = client.get("/alerts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["total_items"] >= 1
    assert payload["items"][0]["entity_type"] == "provider"


def test_get_alert_detail_returns_related_context() -> None:
    client = _client_with_alerts()

    response = client.get("/alerts/alert-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["alert"]["id"] == "alert-001"
    assert payload["policy_citations"][0]["citation_id"] == "policy-17"


def test_acknowledge_alert_returns_scaffold_status() -> None:
    client = _client_with_alerts()

    response = client.post("/alerts/alert-001/acknowledge")

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_get_graph_entity_returns_neighbors_and_relationships() -> None:
    client = TestClient(create_app())

    response = client.get("/graph/entities/provider-204")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity"]["id"] == "provider-204"
    assert payload["neighbors"][0]["type"] == "claim"
    assert payload["relationships"][0]["type"] == "submitted_by"


def test_get_evidence_pack_returns_items_and_scores() -> None:
    client = TestClient(create_app())

    response = client.get("/evidence-packs/evidence-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "evidence-001"
    assert payload["items"][0]["source_type"] == "document"
    assert payload["scores"]["peer_deviation"] == 0.94


def test_get_cases_returns_case_queue() -> None:
    client = TestClient(create_app())

    response = client.get("/cases")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["id"] == "case-1001"
    assert payload["page"]["total_items"] == 2


def test_get_case_detail_returns_alerts_and_feedback() -> None:
    client = TestClient(create_app())

    response = client.get("/cases/case-1001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["case"]["id"] == "case-1001"
    assert payload["alerts"][0]["id"] == "alert-001"
    assert payload["feedback_history"][0]["label"] == "insufficient_evidence"


def test_get_chat_conversation_returns_messages() -> None:
    client = TestClient(create_app())

    response = client.get("/chat/conversations/conversation-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "conversation-001"
    assert payload["messages"][1]["role"] == "assistant"


def test_get_workflows_returns_recent_runs() -> None:
    client = _client_with_workflows()

    response = client.get("/workflows")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["workflow_type"] == "analytics"
    assert payload["items"][0]["current_step"] == "risk_scoring"
    assert payload["items"][1]["status"] == "completed"


def test_get_analytics_overview_returns_dashboard_metrics() -> None:
    client = TestClient(create_app())

    response = client.get("/analytics/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_alerts"] >= 1
    assert payload["entities_monitored"] >= 1
    assert payload["high_risk_entities"] >= 1


def test_get_risk_score_returns_factor_breakdown() -> None:
    client = TestClient(create_app())

    response = client.get("/analytics/risk-scores/provider-204")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-204"
    assert payload["factors"][0]["factor_name"] == "peer_group_deviation"


def test_get_timeseries_returns_chart_points() -> None:
    client = TestClient(create_app())

    response = client.get("/analytics/timeseries/provider-204")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-204"
    assert len(payload["points"]) >= 5
    assert any(point["is_anomaly"] for point in payload["points"])


def test_get_policy_gaps_returns_queue() -> None:
    client = TestClient(create_app())

    response = client.get("/policy/gaps")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["total_items"] >= 1
    assert payload["items"][0]["severity"] in {"critical", "high", "medium"}


def test_get_policy_gap_detail_returns_citations_and_trend() -> None:
    client = TestClient(create_app())

    response = client.get("/policy/gaps/policy-gap-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gap"]["id"] == "policy-gap-001"
    assert len(payload["policy_citations"]) >= 1
    assert len(payload["trend"]) >= 1


def test_get_policy_gap_cases_returns_affected_cases() -> None:
    client = TestClient(create_app())

    response = client.get("/policy/gaps/policy-gap-001/cases")

    assert response.status_code == 200
    payload = response.json()
    assert payload["gap_id"] == "policy-gap-001"
    assert payload["items"][0]["id"] == "case-1001"


def test_create_policy_brief_returns_generated_brief() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/policy/briefs",
        json={
            "gap_id": "policy-gap-001",
            "audience": "Operations leadership",
            "objective": "Summarize why a guidance update is needed.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["gap_id"] == "policy-gap-001"
    assert payload["audience"] == "Operations leadership"
    assert len(payload["recommendations"]) >= 1


def test_workspace_event_stream_returns_snapshot() -> None:
    app = create_app()
    repository = _seed_alert_repository()
    app.dependency_overrides[get_alert_repository] = lambda: repository
    client = TestClient(app)

    response = client.get("/events/stream?max_events=1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    lines = response.text.splitlines()
    event_line = lines[0]
    data_line = lines[1]

    assert event_line == "event: workspace-update"
    assert data_line.startswith("data: ")
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["sequence"] == 0
    assert payload["active_alerts"] >= 1