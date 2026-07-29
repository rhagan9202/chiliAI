"""Tests for Phase 4 scaffold read-model routers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState, WorkflowStepStatus
from agent.service import create_agent_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from api.app import create_app
from api.dependencies import (
    get_agent_service,
    get_alert_feed_store,
    get_graph_service,
    get_knowledge_base_repository,
    get_risk_service,
)
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from graph.protocols import GraphServiceProtocol
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.protocols import KnowledgeBaseRepository
from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.adapters.postgres import PostgresAlertHistoryStore
from monitoring.adapters.protocols import AlertFeedStoreProtocol
from monitoring.models import AlertHistoryRecord
from shared.types import Entity, KnowledgeBase, Relationship
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


def _seed_alert_store() -> AlertFeedStoreProtocol:
    """Return a deterministic durable alert store for API tests."""
    store = InMemoryAlertHistoryWriter()
    created_at = utc_now()
    store.write_alerts(
        [
            AlertHistoryRecord(
                knowledge_base_id="kb-1",
                alert_id="alert-001",
                entity_id="provider-204",
                entity_type="provider",
                severity="critical",
                status="open",
                title="Outlier billing concentration",
                reasoning="Provider activity is materially above peers.",
                metric_name="claims_per_week",
                evidence_pack_id="evidence-001",
                created_at=created_at,
                updated_at=created_at,
                entity_label="Redwood DME Group",
                confidence=0.96,
                tags=["billing", "peer-deviation"],
            ),
            AlertHistoryRecord(
                knowledge_base_id="kb-2",
                alert_id="alert-002",
                entity_id="provider-118",
                entity_type="provider",
                severity="high",
                status="open",
                title="Referral concentration anomaly",
                reasoning="Referral traffic is concentrated outside norms.",
                metric_name="referral_concentration",
                evidence_pack_id=None,
                created_at=created_at - timedelta(minutes=5),
                updated_at=created_at - timedelta(minutes=5),
                entity_label="North Harbor Imaging",
                confidence=0.84,
                tags=["network"],
            ),
        ]
    )
    return store


def _client_with_alerts() -> TestClient:
    """Create a test client whose /alerts route uses the durable store."""
    app = create_app()
    store = _seed_alert_store()
    app.dependency_overrides[get_alert_feed_store] = lambda: store
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


def test_list_alerts_route_passes_status_and_pagination() -> None:
    app = create_app()
    store = _seed_alert_store()
    acknowledged = store.acknowledge("alert-001")
    assert acknowledged is not None
    app.dependency_overrides[get_alert_feed_store] = lambda: store
    client = TestClient(app)

    response = client.get("/alerts", params={"status": "open", "limit": 1, "offset": 0})

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["total_items"] == 1
    assert payload["page"]["page_size"] == 1
    assert [item["id"] for item in payload["items"]] == ["alert-002"]


def test_list_alerts_route_passes_knowledge_base_filter() -> None:
    app = create_app()
    store = _seed_alert_store()
    app.dependency_overrides[get_alert_feed_store] = lambda: store
    client = TestClient(app)

    response = client.get("/alerts", params={"kb": "kb-2", "limit": 1, "offset": 0})

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"]["total_items"] == 1
    assert payload["page"]["page_size"] == 1
    assert [item["id"] for item in payload["items"]] == ["alert-002"]


def test_get_alert_detail_returns_related_context() -> None:
    client = _client_with_alerts()

    response = client.get("/alerts/alert-001", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["alert"]["id"] == "alert-001"
    # AlertHistoryRecord carries no related-entity/policy-citation columns; the
    # detail payload defaults to the alert's own entity and an empty list.
    assert payload["related_entity_ids"] == ["provider-204"]
    assert payload["policy_citations"] == []


def test_acknowledge_alert_returns_scaffold_status() -> None:
    client = _client_with_alerts()

    response = client.post(
        "/alerts/alert-001/acknowledge", params={"knowledge_base_id": "kb-1"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_get_alert_detail_refuses_an_alert_from_another_knowledge_base() -> None:
    """Reading an alert by id must not cross a KB boundary.

    ``/cases/{id}`` and ``/evidence-packs/{id}`` already 404 on a KB mismatch;
    the alert detail route accepted no KB at all, so any caller could read
    another knowledge base's alert body in full.
    """
    client = _client_with_alerts()

    response = client.get("/alerts/alert-002", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 404


def test_acknowledge_refuses_an_alert_from_another_knowledge_base() -> None:
    """The same boundary applies to mutation, not just reads."""
    client = _client_with_alerts()

    response = client.post(
        "/alerts/alert-002/acknowledge", params={"knowledge_base_id": "kb-1"}
    )

    assert response.status_code == 404


def test_alert_detail_requires_a_knowledge_base() -> None:
    """An omitted KB must be rejected, not silently treated as workspace-wide."""
    client = _client_with_alerts()

    assert client.get("/alerts/alert-001").status_code == 422
    assert client.post("/alerts/alert-001/acknowledge").status_code == 422


def _seeded_graph_service() -> GraphServiceProtocol:
    repository = InMemoryGraphRepository()
    repository.upsert_entities(
        "kb-1",
        [
            Entity(
                id="provider-204",
                type="provider",
                properties={"display_name": "Advanced Pain Specialists"},
            ),
            Entity(
                id="claim-8821",
                type="claim",
                properties={"display_name": "Claim 8821"},
            ),
        ],
    )
    repository.upsert_relationships(
        "kb-1",
        [
            Relationship(
                id="rel-1",
                type="submitted_by",
                source_id="claim-8821",
                target_id="provider-204",
            )
        ],
    )
    return create_graph_service(
        repository,
        object_store=InMemoryObjectStore(),
        event_bus=InMemoryEventBus(),
    )


def _seeded_kb_repository(entity_count: int = 2) -> KnowledgeBaseRepository:
    repository = InMemoryKnowledgeBaseRepository()
    repository.create(
        KnowledgeBase(
            id="kb-1",
            name="KB",
            description="Seeded KB",
            entity_count=entity_count,
            status="ready",
            created_at=utc_now(),
        )
    )
    return repository


def _seeded_risk_service() -> RiskServiceProtocol:
    profiles = [
        RiskProfile(
            knowledge_base_id="kb-1",
            entity_id="provider-204",
            signals=[
                RiskSignal(
                    signal_name="peer_group_deviation",
                    value=0.95,
                    weight=2.0,
                    rationale="Exceeds peer benchmark.",
                ),
                RiskSignal(
                    signal_name="network_concentration",
                    value=0.78,
                    weight=1.3,
                    rationale="Narrow referral cluster.",
                ),
            ],
        )
    ]
    return create_risk_service(
        InMemoryRiskSignalSource(profiles=profiles), event_bus=InMemoryEventBus()
    )


def test_get_graph_entity_returns_neighbors_and_relationships() -> None:
    app = create_app()
    graph_service = _seeded_graph_service()
    kb_repository = _seeded_kb_repository()
    risk_service = _seeded_risk_service()
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_risk_service] = lambda: risk_service
    client = TestClient(app)

    response = client.get("/graph/entities/provider-204")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity"]["id"] == "provider-204"
    assert payload["entity"]["risk_score"] > 0.0
    assert payload["neighbors"][0]["type"] == "claim"
    assert payload["relationships"][0]["type"] == "submitted_by"


def test_get_evidence_pack_returns_persisted_pack() -> None:
    from analytics.explainability.adapters.evidence_in_memory import (
        InMemoryEvidencePackRepository,
    )
    from shared.types import EvidenceNarrativeSection, EvidencePack, FeatureAttribution

    app = create_app()
    repository = InMemoryEvidencePackRepository()
    repository.put(
        "kb-1",
        EvidencePack(
            id="ev-1",
            alert_id="al-1",
            reasoning="Elevated peer deviation.",
            subgraph_nodes=["provider-1", "claim-1"],
            subgraph_edges=["rel-1"],
            confidence=0.8,
            scores={"overall": 0.8, "peer_deviation": 0.94},
            attribution=[
                FeatureAttribution(
                    feature_name="claim_volume_z", contribution=-0.12, rationale="below peer median"
                )
            ],
            narrative_sections=[
                EvidenceNarrativeSection(
                    heading="Risk Factor", body="Claim volume trails peers.", evidence_refs=["claim-1"]
                )
            ],
        ),
    )
    repository.put(
        "kb-1",
        EvidencePack(
            id="ev-legacy",
            alert_id="al-2",
            reasoning="Legacy pack without enrichment fields.",
            subgraph_nodes=["provider-2"],
            subgraph_edges=[],
            confidence=0.6,
        ),
    )
    app.state.evidence_pack_repository = repository
    client = TestClient(app)

    response = client.get("/evidence-packs/ev-1", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "ev-1"
    assert payload["subgraph_node_ids"] == ["provider-1", "claim-1"]
    assert payload["scores"]["peer_deviation"] == 0.94
    assert payload["attribution"] == [
        {"feature_name": "claim_volume_z", "contribution": -0.12, "rationale": "below peer median"}
    ]
    assert payload["narrative_sections"] == [
        {"heading": "Risk Factor", "body": "Claim volume trails peers.", "evidence_refs": ["claim-1"]}
    ]

    legacy_response = client.get(
        "/evidence-packs/ev-legacy", params={"knowledge_base_id": "kb-1"}
    )

    assert legacy_response.status_code == 200
    legacy_payload = legacy_response.json()
    assert legacy_payload["attribution"] == []
    assert legacy_payload["narrative_sections"] == []


def test_export_evidence_pack_renders_markdown_and_json() -> None:
    """The pack could not leave the browser before (UXA-405)."""
    from analytics.explainability.adapters.evidence_in_memory import (
        InMemoryEvidencePackRepository,
    )
    from shared.types import EvidencePack

    app = create_app()
    repository = InMemoryEvidencePackRepository()
    repository.put(
        "kb-1",
        EvidencePack(
            id="ev-1",
            alert_id="al-1",
            reasoning="Claim volume trails peers.",
            subgraph_nodes=["provider-1"],
            subgraph_edges=[],
            confidence=0.42,
            scores={"peer_deviation": 0.94},
            source_documents=["doc-1"],
        ),
    )
    app.state.evidence_pack_repository = repository
    client = TestClient(app)
    kb = {"knowledge_base_id": "kb-1"}

    markdown = client.get("/evidence-packs/ev-1/export", params={**kb, "format": "markdown"})

    assert markdown.status_code == 200
    body = markdown.json()
    assert body["evidence_pack_id"] == "ev-1"
    assert body["format"] == "markdown"
    # Server-chosen so the download name is one decision in one place.
    assert body["filename"] == "evidence-ev-1.md"
    assert "# Evidence pack ev-1" in body["content"]
    assert "**Peer deviation:** 0.94" in body["content"]
    assert "`doc-1`" in body["content"]

    as_json = client.get("/evidence-packs/ev-1/export", params={**kb, "format": "json"})

    assert as_json.status_code == 200
    json_body = as_json.json()
    assert json_body["filename"] == "evidence-ev-1.json"
    # Machine-readable: the stored pack round-trips.
    assert json.loads(json_body["content"])["scores"]["peer_deviation"] == 0.94


def test_export_evidence_pack_defaults_to_markdown() -> None:
    from analytics.explainability.adapters.evidence_in_memory import (
        InMemoryEvidencePackRepository,
    )
    from shared.types import EvidencePack

    app = create_app()
    repository = InMemoryEvidencePackRepository()
    repository.put(
        "kb-1",
        EvidencePack(
            id="ev-1",
            alert_id="al-1",
            reasoning="x",
            subgraph_nodes=[],
            subgraph_edges=[],
            confidence=0.5,
        ),
    )
    app.state.evidence_pack_repository = repository

    response = TestClient(app).get(
        "/evidence-packs/ev-1/export", params={"knowledge_base_id": "kb-1"}
    )

    assert response.json()["format"] == "markdown"


def test_export_evidence_pack_404s_for_an_unknown_pack() -> None:
    response = TestClient(create_app()).get(
        "/evidence-packs/nope/export", params={"knowledge_base_id": "kb-1"}
    )

    assert response.status_code == 404


def test_get_evidence_pack_returns_404_when_not_persisted() -> None:
    # De-seed regression (BL-005): the previously seeded evidence-001 pack is no
    # longer served; the endpoint reads only from the persisted repository.
    client = TestClient(create_app())

    response = client.get(
        "/evidence-packs/evidence-001", params={"knowledge_base_id": "kb-1"}
    )

    assert response.status_code == 404


def test_get_cases_returns_kb_scoped_queue() -> None:
    client = TestClient(create_app())

    created = client.post(
        "/cases",
        params={"knowledge_base_id": "kb-1"},
        json={"title": "Escalation", "priority": "high", "alert_ids": []},
    )
    assert created.status_code == 200
    case_id = created.json()["case"]["id"]

    response = client.get("/cases", params={"knowledge_base_id": "kb-1"})
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [case_id]
    assert payload["items"][0]["knowledge_base_id"] == "kb-1"

    # KB isolation: a different KB sees none of kb-1's cases.
    other = client.get("/cases", params={"knowledge_base_id": "kb-2"})
    assert other.json()["items"] == []


def test_get_case_detail_returns_durable_case() -> None:
    app = create_app()
    alert_repository = _seed_alert_store()
    app.dependency_overrides[get_alert_feed_store] = lambda: alert_repository
    client = TestClient(app)

    created = client.post(
        "/cases",
        params={"knowledge_base_id": "kb-1"},
        json={"title": "Escalation", "priority": "high", "alert_ids": ["alert-001"]},
    )
    case_id = created.json()["case"]["id"]

    response = client.get(
        f"/cases/{case_id}", params={"knowledge_base_id": "kb-1"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["case"]["id"] == case_id
    assert payload["case"]["knowledge_base_id"] == "kb-1"
    assert payload["alerts"][0]["id"] == "alert-001"
    assert payload["alerts"][0]["knowledge_base_id"] == "kb-1"
    assert payload["alerts"][0]["entity_label"] == "Redwood DME Group"
    assert payload["alerts"][0]["tags"] == ["billing", "peer-deviation"]

    # Unknown case (or wrong KB) is a 404.
    assert (
        client.get(f"/cases/{case_id}", params={"knowledge_base_id": "kb-2"}).status_code
        == 404
    )


def test_get_chat_conversation_returns_messages() -> None:
    client = TestClient(create_app())

    created = client.post(
        "/chat/conversations",
        json={"knowledge_base_id": "kb-1", "title": "Provider anomaly review"},
    )
    assert created.status_code == 200
    conversation_id = created.json()["id"]
    sent = client.post(
        f"/chat/conversations/{conversation_id}/messages",
        params={"knowledge_base_id": "kb-1"},
        json={"content": "Why is provider-204 risky?"},
    )
    assert sent.status_code == 200

    response = client.get(
        f"/chat/conversations/{conversation_id}",
        params={"knowledge_base_id": "kb-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == conversation_id
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
    app = create_app()
    alert_repository = _seed_alert_store()
    kb_repository = _seeded_kb_repository(entity_count=4)
    app.dependency_overrides[get_alert_feed_store] = lambda: alert_repository
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    client = TestClient(app)

    # An open case so the overview reflects durable case state.
    client.post(
        "/cases",
        params={"knowledge_base_id": "kb-1"},
        json={"title": "Escalation", "priority": "high", "alert_ids": []},
    )

    response = client.get("/analytics/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_alerts"] >= 1
    assert payload["open_cases"] >= 1
    assert payload["entities_monitored"] == 4
    # alert-001 is critical -> counts as a high-risk active alert.
    assert payload["high_risk_entities"] >= 1


def test_get_risk_score_returns_unavailable_without_registered_signals() -> None:
    """B2 moved the risk detail route off ApiState's seeded profiles onto the
    DI risk service. No derived signals are registered for a fresh app, so the
    route must report availability_status == "unavailable" rather than serving
    stale seed data.
    """
    client = TestClient(create_app())

    response = client.get("/analytics/risk-scores/provider-204", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-204"
    assert payload["availability_status"] == "unavailable"
    assert payload["factors"] == []


def test_get_timeseries_returns_unavailable_without_configured_data() -> None:
    """B2 (analytics.07) moved the entity timeseries route off ApiState's
    seeded chart points onto record-aggregate series + persisted anomalies.
    The default domain pack configures no timeseries metric specs and no
    record data has been ingested, so the route must report
    availability_status == "unavailable" rather than serving stale seed data.
    """
    client = TestClient(create_app())

    response = client.get("/analytics/timeseries/provider-204", params={"knowledge_base_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-204"
    assert payload["points"] == []
    assert payload["availability_status"] == "unavailable"
    assert payload["metric_name"] == "timeseries"


def test_workspace_event_stream_returns_snapshot() -> None:
    app = create_app()
    repository = _seed_alert_store()
    app.dependency_overrides[get_alert_feed_store] = lambda: repository
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


@pytest.mark.integration
def test_alert_routes_are_durable_against_postgres() -> None:
    """Request-level proof that the alert feed reads/writes real rows through
    ``PostgresAlertHistoryStore``, not just the in-memory adapter (alerts.36):
    write via the store, GET /alerts returns it, POST ack durably updates the
    row (re-read via a FRESH store instance)."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not set; skipping Postgres alert route test.")

    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    kb_id = f"kb-alert-router-integration-{uuid4()}"
    alert_id = f"alert-{uuid4()}"
    now = utc_now()
    try:
        store = PostgresAlertHistoryStore(provider)
        store.write_alerts(
            [
                AlertHistoryRecord(
                    knowledge_base_id=kb_id,
                    alert_id=alert_id,
                    entity_id="provider-204",
                    entity_type="provider",
                    severity="critical",
                    status="open",
                    title="Outlier billing concentration",
                    reasoning="Provider activity is materially above peers.",
                    metric_name="claims_per_week",
                    evidence_pack_id="evidence-001",
                    created_at=now,
                    updated_at=now,
                    entity_label="Redwood DME Group",
                    confidence=0.96,
                    tags=["billing", "peer-deviation"],
                )
            ]
        )

        app = create_app()
        app.dependency_overrides[get_alert_feed_store] = lambda: store
        client = TestClient(app)

        list_response = client.get("/alerts", params={"kb": kb_id})
        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert [item["id"] for item in list_payload["items"]] == [alert_id]
        assert list_payload["items"][0]["entity_label"] == "Redwood DME Group"
        assert list_payload["items"][0]["confidence"] == 0.96
        assert list_payload["items"][0]["tags"] == ["billing", "peer-deviation"]

        ack_response = client.post(
            f"/alerts/{alert_id}/acknowledge", params={"knowledge_base_id": kb_id}
        )
        assert ack_response.status_code == 200
        assert ack_response.json()["status"] == "accepted"

        # Re-read through a FRESH store instance to prove the acknowledgement
        # durably committed to Postgres, not just an in-process cache.
        fresh_store = PostgresAlertHistoryStore(provider)
        reread = fresh_store.get_alert(alert_id)
        assert reread is not None
        assert reread.status == "acknowledged"
    finally:
        with provider.connection() as conn:
            conn.execute(
                "DELETE FROM alert_history WHERE knowledge_base_id = %s",
                (kb_id,),
            )
            conn.commit()
        provider.close()
