"""Tests for service-backed Phase 5 routes and persisted write flows."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from analytics.peerstats.models import PeerAggregate
from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal
from analytics.risk.service import create_risk_service
from analytics.timeseries.adapters.in_memory import InMemoryTimeseriesAnomalyStore
from analytics.timeseries.adapters.protocols import TimeseriesAnomalyStoreProtocol
from analytics.timeseries.adapters.record_aggregates import RecordAggregateTimeSeriesSource
from analytics.timeseries.models import TimeseriesAnomalyRecord
from api.app import create_app
from api.dependencies import (
    get_alert_feed_store,
    get_entity_series_source,
    get_graph_service,
    get_knowledge_base_repository,
    get_risk_service,
    get_timeseries_anomaly_store,
)
from config.schema import TimeseriesMetricSpec
from events.adapters.in_memory import InMemoryEventBus
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import create_graph_service
from graph.protocols import GraphServiceProtocol
from knowledgebases.adapters.in_memory import InMemoryKnowledgeBaseRepository
from knowledgebases.protocols import KnowledgeBaseRepository
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.models import AlertHistoryRecord
from shared.types import Entity, KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


def _second_alert_record() -> AlertHistoryRecord:
    """A second durable alert in the same KB, for attach-to-case (UXA-405)."""
    now = utc_now()
    return AlertHistoryRecord(
        knowledge_base_id="kb-1",
        alert_id="alert-002",
        entity_id="provider-204",
        entity_type="provider",
        severity="high",
        status="open",
        title="Repeat billing spike",
        reasoning="The same provider spiked again the following week.",
        metric_name="claims_per_week",
        evidence_pack_id="evidence-002",
        created_at=now,
        updated_at=now,
        entity_label="Redwood DME Group",
        confidence=0.88,
        tags=["billing"],
    )


def _client_with_alert_history(
    extra: list[AlertHistoryRecord] | None = None,
) -> TestClient:
    """Create a test client with a deterministic durable alert row."""
    app = create_app()
    store = InMemoryAlertHistoryWriter()
    now = utc_now()
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
                created_at=now,
                updated_at=now,
                entity_label="Redwood DME Group",
                confidence=0.96,
                tags=["billing"],
            )
        ]
    )
    if extra:
        store.write_alerts(extra)
    app.dependency_overrides[get_alert_feed_store] = lambda: store
    return TestClient(app)


def test_alert_acknowledgement_changes_status() -> None:
    client = _client_with_alert_history()

    alerts = client.get("/alerts").json()["items"]
    alert_id = alerts[0]["id"]
    kb = {"knowledge_base_id": alerts[0]["knowledge_base_id"]}

    response = client.post(f"/alerts/{alert_id}/acknowledge", params=kb)

    assert response.status_code == 200
    updated = client.get(f"/alerts/{alert_id}", params=kb).json()
    assert updated["alert"]["status"] == "acknowledged"


def test_create_and_update_case_and_append_feedback() -> None:
    client = _client_with_alert_history()

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
            "label": "insufficient_evidence",
            "evidence_adequacy": "low",
            "missing_evidence": ["prior authorization records"],
            "notes": "Need authorization records before escalation.",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["feedback_history"][-1]["label"] == "insufficient_evidence"

    # Fresh detail must be backed by the durable case record, not the legacy
    # app-state feedback cache.
    cast(FastAPI, client.app).state.case_feedback = {}
    detail = client.get(f"/cases/{case_id}", params=kb)
    assert detail.status_code == 200
    saved_feedback = detail.json()["feedback_history"][-1]
    assert saved_feedback["label"] == "insufficient_evidence"
    assert saved_feedback["evidence_adequacy"] == "low"
    assert saved_feedback["missing_evidence"] == ["prior authorization records"]
    assert saved_feedback["notes"] == "Need authorization records before escalation."


def test_promote_alert_to_case_captures_origin_and_evidence() -> None:
    client = _client_with_alert_history()

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
    assert promoted.json()["alerts"][0]["id"] == "alert-001"
    assert promoted.json()["alerts"][0]["knowledge_base_id"] == "kb-1"
    # Timeline snapshot captured from the originating alert.
    assert promoted.json()["entity_timeline"][0]["label"] == "alert_raised"

    detail = client.get(f"/cases/{case['id']}", params={"knowledge_base_id": "kb-1"})
    assert detail.status_code == 200
    assert detail.json()["alerts"][0]["id"] == "alert-001"
    assert detail.json()["alerts"][0]["knowledge_base_id"] == "kb-1"

    # The promoted case is now listed under its KB.
    listed = client.get("/cases", params={"knowledge_base_id": "kb-1"}).json()
    assert [item["id"] for item in listed["items"]] == [case["id"]]


def test_promote_unknown_alert_returns_404() -> None:
    client = _client_with_alert_history()

    response = client.post(
        "/cases/promote",
        params={"knowledge_base_id": "kb-1"},
        json={"alert_id": "missing-alert"},
    )

    assert response.status_code == 404


def test_promote_alert_from_different_knowledge_base_returns_404_without_case() -> None:
    client = _client_with_alert_history()

    response = client.post(
        "/cases/promote",
        params={"knowledge_base_id": "kb-2"},
        json={"alert_id": "alert-001"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Alert not found."

    listed = client.get("/cases", params={"knowledge_base_id": "kb-2"})
    assert listed.status_code == 200
    assert listed.json()["items"] == []


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
        params={"knowledge_base_id": "kb-1"},
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


class _SeededColumnSource:
    """Protocol double returning canned aggregates for one entity (Task 3's shape)."""

    def __init__(self, aggregates: list[PeerAggregate]) -> None:
        self._aggregates = aggregates

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: object,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        del knowledge_base_id, spec, interval_starts
        return self._aggregates


def _seeded_entity_series_source(
    entity_id: str,
) -> tuple[RecordAggregateTimeSeriesSource, TimeseriesAnomalyStoreProtocol]:
    """Build a record-aggregate series (with a persisted anomaly) for one entity."""
    spec = TimeseriesMetricSpec(
        name="weekly_billing_self",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="npi",
        value_column="amount",
        aggregation="sum",
        interval="week",
        time_column="service_date",
    )
    anomaly_bucket = datetime(2026, 1, 15, tzinfo=timezone.utc)
    aggregates = [
        PeerAggregate(
            entity_id=entity_id,
            entity_type="provider",
            peer_group_key="provider",
            interval_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            aggregate_value=100.0,
        ),
        PeerAggregate(
            entity_id=entity_id,
            entity_type="provider",
            peer_group_key="provider",
            interval_start=datetime(2026, 1, 8, tzinfo=timezone.utc),
            aggregate_value=120.0,
        ),
        PeerAggregate(
            entity_id=entity_id,
            entity_type="provider",
            peer_group_key="provider",
            interval_start=anomaly_bucket,
            aggregate_value=400.0,
        ),
    ]
    source = RecordAggregateTimeSeriesSource(_SeededColumnSource(aggregates), specs=[spec])
    anomaly_store = InMemoryTimeseriesAnomalyStore()
    anomaly_store.write_anomalies(
        [
            TimeseriesAnomalyRecord(
                knowledge_base_id="kb-1",
                entity_id=entity_id,
                metric_name=spec.name,
                observed_at=anomaly_bucket,
                observed_value=400.0,
                expected_value=110.0,
                z_score=3.4,
                severity=0.9,
                detection_strategy="z_score",
                correlation_id="corr-service-backed",
            )
        ]
    )
    return source, anomaly_store


def test_graph_and_analytics_routes_are_service_backed() -> None:
    app = create_app()
    store = InMemoryAlertHistoryWriter()
    now = utc_now()
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
                created_at=now,
                updated_at=now,
                entity_label="Redwood DME Group",
                confidence=0.96,
                tags=["billing"],
            )
        ]
    )
    app.dependency_overrides[get_alert_feed_store] = lambda: store
    graph_service = _seeded_graph_service("provider-204")
    kb_repository = _seeded_kb_repository()
    entity_series_source, anomaly_store = _seeded_entity_series_source("provider-204")
    app.dependency_overrides[get_graph_service] = lambda: graph_service
    app.dependency_overrides[get_knowledge_base_repository] = lambda: kb_repository
    app.dependency_overrides[get_entity_series_source] = lambda: entity_series_source
    app.dependency_overrides[get_timeseries_anomaly_store] = lambda: anomaly_store
    risk_service = create_risk_service(
        InMemoryRiskSignalSource(
            profiles=[
                RiskProfile(
                    knowledge_base_id="kb-1",
                    entity_id="provider-204",
                    signals=[
                        RiskSignal(signal_name="peer_group_deviation", value=0.9, weight=1.5),
                        RiskSignal(
                            signal_name="timeseries_anomaly:monthly_inpatient_billing_self",
                            value=0.7,
                            weight=1.0,
                        ),
                    ],
                )
            ]
        ),
        event_bus=InMemoryEventBus(),
    )
    app.dependency_overrides[get_risk_service] = lambda: risk_service
    client = TestClient(app)

    alerts = client.get("/alerts").json()["items"]
    entity_id = alerts[0]["entity_id"]
    evidence_id = alerts[0]["evidence_pack_id"]

    graph_detail = client.get(f"/graph/entities/{entity_id}")
    risk_score = client.get(f"/analytics/risk-scores/{entity_id}", params={"knowledge_base_id": "kb-1"})
    timeseries = client.get(f"/analytics/timeseries/{entity_id}", params={"knowledge_base_id": "kb-1"})
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


def test_attach_alert_adds_to_an_existing_case_without_moving_its_origin() -> None:
    """Promote opens a case; attach adds to one that exists (UXA-405)."""
    client = _client_with_alert_history(extra=[_second_alert_record()])
    kb = {"knowledge_base_id": "kb-1"}
    case_id = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"}).json()[
        "case"
    ]["id"]

    attached = client.post(
        f"/cases/{case_id}/alerts",
        params=kb,
        json={"alert_id": "alert-002", "notes": "Same provider, following week."},
    )

    assert attached.status_code == 200
    body = attached.json()
    assert body["case"]["alert_ids"] == ["alert-001", "alert-002"]
    # The case still records what it was opened from.
    assert body["case"]["originating_alert_id"] == "alert-001"
    assert body["case"]["evidence_pack_id"] == "evidence-001"
    assert {alert["id"] for alert in body["alerts"]} == {"alert-001", "alert-002"}
    timeline = body["entity_timeline"][-1]
    assert timeline["label"] == "Alert attached"
    assert "Same provider, following week." in timeline["detail"]

    # Durable, not just echoed back.
    detail = client.get(f"/cases/{case_id}", params=kb).json()
    assert detail["case"]["alert_ids"] == ["alert-001", "alert-002"]


def test_attach_alert_rejects_a_duplicate_with_409() -> None:
    client = _client_with_alert_history()
    kb = {"knowledge_base_id": "kb-1"}
    case_id = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"}).json()[
        "case"
    ]["id"]

    again = client.post(f"/cases/{case_id}/alerts", params=kb, json={"alert_id": "alert-001"})

    assert again.status_code == 409


def test_attach_alert_404s_for_unknown_case_or_alert() -> None:
    client = _client_with_alert_history()
    kb = {"knowledge_base_id": "kb-1"}
    case_id = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"}).json()[
        "case"
    ]["id"]

    unknown_case = client.post("/cases/ghost/alerts", params=kb, json={"alert_id": "alert-001"})
    unknown_alert = client.post(
        f"/cases/{case_id}/alerts", params=kb, json={"alert_id": "nope"}
    )
    other_kb = client.post(
        f"/cases/{case_id}/alerts",
        params={"knowledge_base_id": "kb-2"},
        json={"alert_id": "alert-001"},
    )

    assert unknown_case.status_code == 404
    assert unknown_alert.status_code == 404
    # An alert outside the requested KB scope is not reachable either.
    assert other_kb.status_code == 404
