"""Tests for Phase 4 scaffold read-model routers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from agent.adapters.in_memory import InMemoryWorkflowRunStore
from agent.models import WorkflowRun, WorkflowRunStatus, WorkflowStepState, WorkflowStepStatus
from agent.service import create_agent_service
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.protocols import RiskServiceProtocol
from analytics.risk.service import create_risk_service
from api._alert_store import AlertProjectionRecord, InMemoryAlertProjectionRepository
from api.app import create_app
from api.contracts import PolicyCitation
from api.dependencies import (
    get_agent_service,
    get_alert_repository,
    get_graph_service,
    get_knowledge_base_repository,
    get_risk_service,
)
from api.routers.alerts import list_alerts as list_alerts_route
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from graph.protocols import GraphServiceProtocol
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.protocols import KnowledgeBaseRepository
from shared.types import Alert, Entity, KnowledgeBase, Relationship
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


def _seed_alert_repository() -> InMemoryAlertProjectionRepository:
    """Return a deterministic alert projection repository for API tests."""
    repository = InMemoryAlertProjectionRepository()
    created_at = utc_now()
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
            knowledge_base_id="kb-2",
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


def test_list_alerts_route_passes_status_and_pagination() -> None:
    repository = _seed_alert_repository()
    acknowledge_alert = repository.acknowledge("alert-001")
    assert acknowledge_alert is not None

    payload = asyncio.run(
        list_alerts_route(
            status_filter="open",
            limit=1,
            offset=0,
            repository=repository,
        )
    )

    assert payload.page.total_items == 1
    assert payload.page.page_size == 1
    assert [item.id for item in payload.items] == ["alert-002"]


def test_list_alerts_route_passes_knowledge_base_filter() -> None:
    repository = _seed_alert_repository()

    payload = asyncio.run(
        list_alerts_route(
            knowledge_base_id="kb-2",
            status_filter=None,
            limit=1,
            offset=0,
            repository=repository,
        )
    )

    assert payload.page.total_items == 1
    assert payload.page.page_size == 1
    assert [item.id for item in payload.items] == ["alert-002"]


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
    from shared.types import EvidencePack

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
    alert_repository = _seed_alert_repository()
    app.dependency_overrides[get_alert_repository] = lambda: alert_repository
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
        json={"content": "Why is provider-204 risky?"},
    )
    assert sent.status_code == 200

    response = client.get(f"/chat/conversations/{conversation_id}")

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
    alert_repository = _seed_alert_repository()
    kb_repository = _seeded_kb_repository(entity_count=4)
    app.dependency_overrides[get_alert_repository] = lambda: alert_repository
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


def test_get_risk_score_returns_factor_breakdown() -> None:
    client = TestClient(create_app())

    response = client.get("/analytics/risk-scores/provider-204", params={"kb_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-204"
    assert payload["factors"][0]["factor_name"] == "peer_group_deviation"


def test_get_timeseries_returns_unavailable_without_configured_data() -> None:
    """B2 (analytics.07) moved the entity timeseries route off ApiState's
    seeded chart points onto record-aggregate series + persisted anomalies.
    The default domain pack configures no timeseries metric specs and no
    record data has been ingested, so the route must report
    availability_status == "unavailable" rather than serving stale seed data.
    """
    client = TestClient(create_app())

    response = client.get("/analytics/timeseries/provider-204", params={"kb_id": "kb-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_id"] == "provider-204"
    assert payload["points"] == []
    assert payload["availability_status"] == "unavailable"
    assert payload["metric_name"] == "timeseries"


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
