"""Tests for Phase 4 scaffold read-model routers."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api.app import create_app


def test_get_alerts_returns_paginated_feed() -> None:
    client = TestClient(create_app())

    response = client.get("/alerts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["total_items"] >= 1
    assert payload["items"][0]["entity_type"] == "provider"


def test_get_alert_detail_returns_related_context() -> None:
    client = TestClient(create_app())

    response = client.get("/alerts/alert-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["alert"]["id"] == "alert-001"
    assert payload["policy_citations"][0]["citation_id"] == "policy-17"


def test_acknowledge_alert_returns_scaffold_status() -> None:
    client = TestClient(create_app())

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
    client = TestClient(create_app())

    response = client.get("/workflows")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["workflow_type"] == "analytics"
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
    client = TestClient(create_app())

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