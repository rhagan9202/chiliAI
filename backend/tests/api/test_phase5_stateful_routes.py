"""Tests for service-backed Phase 5 routes and persisted write flows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from analytics.explainability.adapters.evidence_in_memory import (
    InMemoryEvidencePackRepository,
)
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
    get_evidence_pack_repository,
    get_explanation_review_service,
    get_graph_service,
    get_knowledge_base_repository,
    get_risk_service,
    get_timeseries_anomaly_store,
)
from api.middleware.auth import User, get_current_user
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEvent, AuditEventQuery
from auditlog.service import AuditLogService
from analytics.explainability.reviews import (
    ExplanationReviewCreate,
    ExplanationReviewService,
    ExplanationReviewTarget,
    InMemoryExplanationReviewRepository,
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
from shared.types import Entity, EvidencePack, EvidenceProvenanceReference, KnowledgeBase
from shared.utils import utc_now
from storage.adapters.in_memory import InMemoryObjectStore


class _FailingAuditRepository(InMemoryAuditLogRepository):
    def append(self, event: AuditEvent) -> None:
        raise RuntimeError("audit sink unavailable")


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
    evidence_repository: InMemoryEvidencePackRepository | None = None,
    review_service: ExplanationReviewService | None = None,
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
    if evidence_repository is not None:
        app.dependency_overrides[get_evidence_pack_repository] = lambda: evidence_repository
    if review_service is not None:
        app.dependency_overrides[get_explanation_review_service] = lambda: review_service
    return TestClient(app)


def _evidence_pack(
    evidence_pack_id: str,
    *,
    alert_id: str,
    reasoning: str,
    provenance_label: str,
) -> EvidencePack:
    return EvidencePack(
        id=evidence_pack_id,
        alert_id=alert_id,
        reasoning=reasoning,
        subgraph_nodes=["provider-204"],
        subgraph_edges=[],
        confidence=0.91,
        provenance=[
            EvidenceProvenanceReference(
                reference_type="document",
                reference_id=f"{evidence_pack_id}#source:0",
                label=provenance_label,
                source_system="cms-claims",
                source_version="2026-08-demo",
                transformation_version="safe-cms-008-test",
                confidence=0.91,
                route_target="/knowledgebases/kb-1/documents/source-doc/preview",
                metadata={"document_id": "source-doc"},
            )
        ],
        source_documents=["source-doc"],
    )


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


def test_case_create_update_and_feedback_record_audit_events() -> None:
    client = _client_with_alert_history()
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    cast(FastAPI, client.app).state.audit_log_service = audit_service
    cast(FastAPI, client.app).dependency_overrides[get_current_user] = lambda: User(
        user_id="analyst-42",
        roles=["analyst"],
        email="analyst42@example.test",
    )

    alert_id = client.get("/alerts").json()["items"][0]["id"]
    kb = {"knowledge_base_id": "kb-1"}
    created = client.post(
        "/cases",
        params=kb,
        json={
            "title": "Audited escalation",
            "priority": "medium",
            "assignee": "J. Chen",
            "alert_ids": [alert_id],
        },
    )
    assert created.status_code == 200
    case_id = created.json()["case"]["id"]

    updated = client.patch(
        f"/cases/{case_id}",
        params=kb,
        json={"status": "in_review", "priority": "high"},
    )
    assert updated.status_code == 200
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

    page = audit_service.list_events(
        AuditEventQuery(knowledge_base_id="kb-1")
    )
    assert [event.action for event in page.items] == [
        "case.feedback.create",
        "case.update",
        "case.create",
    ]
    assert {event.actor_user_id for event in page.items} == {"analyst-42"}
    assert page.items[0].resource_id == case_id
    assert page.items[0].before == {"feedback_count": 0}
    assert page.items[0].after == {
        "feedback_count": 1,
        "label": "insufficient_evidence",
        "evidence_adequacy": "low",
        "missing_evidence_count": 1,
    }
    assert page.items[1].before == {"status": "open", "priority": "medium"}
    assert page.items[1].after == {"status": "in_review", "priority": "high"}
    assert page.items[2].before is None
    assert page.items[2].after == {
        "status": "open",
        "priority": "medium",
        "alert_count": 1,
    }


def test_case_promote_and_attach_record_audit_events() -> None:
    client = _client_with_alert_history(extra=[_second_alert_record()])
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    cast(FastAPI, client.app).state.audit_log_service = audit_service
    cast(FastAPI, client.app).dependency_overrides[get_current_user] = lambda: User(
        user_id="analyst-42",
        roles=["analyst"],
        email="analyst42@example.test",
    )
    kb = {"knowledge_base_id": "kb-1"}

    promoted = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"})
    assert promoted.status_code == 200
    case_id = promoted.json()["case"]["id"]
    attached = client.post(
        f"/cases/{case_id}/alerts",
        params=kb,
        json={"alert_id": "alert-002", "notes": "Same provider, following week."},
    )
    assert attached.status_code == 200

    page = audit_service.list_events(
        AuditEventQuery(knowledge_base_id="kb-1")
    )
    assert [event.action for event in page.items] == [
        "case.alert.attach",
        "case.promote",
    ]
    assert page.items[0].resource_id == case_id
    assert page.items[0].before == {"alert_count": 1, "alert_ids": ["alert-001"]}
    assert page.items[0].after == {
        "alert_count": 2,
        "alert_ids": ["alert-001", "alert-002"],
        "attached_alert_id": "alert-002",
    }
    assert page.items[1].before is None
    assert page.items[1].after == {
        "status": "open",
        "priority": "critical",
        "originating_alert_id": "alert-001",
        "evidence_pack_id": "evidence-001",
    }


def test_case_mutation_still_succeeds_when_audit_sink_fails() -> None:
    client = _client_with_alert_history()
    audit_service = AuditLogService(_FailingAuditRepository())
    cast(FastAPI, client.app).state.audit_log_service = audit_service
    kb = {"knowledge_base_id": "kb-1"}

    response = client.post(
        "/cases",
        params=kb,
        json={"title": "Audit failure tolerated", "priority": "medium"},
    )

    assert response.status_code == 200
    assert audit_service.failed_write_count == 1
    detail = client.get(
        f"/cases/{response.json()['case']['id']}",
        params=kb,
    )
    assert detail.status_code == 200


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


def test_case_dossier_includes_evidence_feedback_and_export_metadata() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put(
        "kb-1",
        _evidence_pack(
            "evidence-001",
            alert_id="alert-001",
            reasoning="Originating alert evidence.",
            provenance_label="Origin claim source",
        ),
    )
    evidence_repository.put(
        "kb-1",
        _evidence_pack(
            "evidence-002",
            alert_id="alert-002",
            reasoning="Attached alert evidence.",
            provenance_label="Attached claim source",
        ),
    )
    client = _client_with_alert_history(
        extra=[_second_alert_record()],
        evidence_repository=evidence_repository,
    )
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    cast(FastAPI, client.app).state.audit_log_service = audit_service
    cast(FastAPI, client.app).dependency_overrides[get_current_user] = lambda: User(
        user_id="analyst-42",
        roles=["analyst"],
        email="analyst42@example.test",
    )
    kb = {"knowledge_base_id": "kb-1"}
    promoted = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"})
    assert promoted.status_code == 200
    case_id = promoted.json()["case"]["id"]
    attached = client.post(
        f"/cases/{case_id}/alerts",
        params=kb,
        json={"alert_id": "alert-002", "notes": "Same provider, later spike"},
    )
    assert attached.status_code == 200
    feedback = client.post(
        f"/cases/{case_id}/feedback",
        params=kb,
        json={
            "label": "insufficient_evidence",
            "evidence_adequacy": "medium",
            "missing_evidence": ["supplier invoice"],
            "notes": "Need invoice before referral.",
        },
    )
    assert feedback.status_code == 200

    dossier = client.get(f"/cases/{case_id}/dossier", params=kb)

    assert dossier.status_code == 200
    payload = dossier.json()
    assert payload["case"]["id"] == case_id
    assert [alert["id"] for alert in payload["alerts"]] == ["alert-001", "alert-002"]
    assert [pack["id"] for pack in payload["evidence_packs"]] == [
        "evidence-001",
        "evidence-002",
    ]
    assert payload["evidence_packs"][0]["provenance"][0]["label"] == "Origin claim source"
    assert payload["entity_timeline"][0]["label"] == "alert_raised"
    assert payload["entity_timeline"][-1]["label"] == "Alert attached"
    assert payload["feedback_history"][0]["notes"] == "Need invoice before referral."
    assert [event["action"] for event in payload["audit_events"]] == [
        "case.feedback.create",
        "case.alert.attach",
        "case.promote",
    ]
    assert {event["actor_user_id"] for event in payload["audit_events"]} == {
        "analyst-42"
    }
    assert payload["audit_events"][0]["resource_type"] == "case"
    assert payload["audit_events"][0]["resource_id"] == case_id
    assert "Need invoice before referral." not in json.dumps(payload["audit_events"])
    assert payload["export"]["formats"] == ["markdown", "json"]
    assert payload["export"]["default_filename"] == f"case-{case_id}.md"

    wrong_kb = client.get(
        f"/cases/{case_id}/dossier", params={"knowledge_base_id": "kb-2"}
    )
    assert wrong_kb.status_code == 404


def test_case_dossier_export_renders_markdown_and_json() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put(
        "kb-1",
        _evidence_pack(
            "evidence-001",
            alert_id="alert-001",
            reasoning="Originating alert evidence.",
            provenance_label="Origin claim source",
        ),
    )
    client = _client_with_alert_history(evidence_repository=evidence_repository)
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    cast(FastAPI, client.app).state.audit_log_service = audit_service
    cast(FastAPI, client.app).dependency_overrides[get_current_user] = lambda: User(
        user_id="analyst-42",
        roles=["analyst"],
        email="analyst42@example.test",
    )
    kb = {"knowledge_base_id": "kb-1"}
    promoted = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"})
    assert promoted.status_code == 200
    case_id = promoted.json()["case"]["id"]
    feedback = client.post(
        f"/cases/{case_id}/feedback",
        params=kb,
        json={
            "label": "suspicious",
            "evidence_adequacy": "high",
            "missing_evidence": [],
            "notes": "Evidence is ready for supervisor review.",
        },
    )
    assert feedback.status_code == 200

    markdown = client.get(
        f"/cases/{case_id}/dossier/export",
        params={**kb, "format": "markdown"},
    )
    assert markdown.status_code == 200
    markdown_payload = markdown.json()
    assert markdown_payload["case_id"] == case_id
    assert markdown_payload["knowledge_base_id"] == "kb-1"
    assert markdown_payload["format"] == "markdown"
    assert markdown_payload["filename"] == f"case-{case_id}.md"
    assert "Investigation: Outlier billing concentration" in markdown_payload["content"]
    assert "Status: open" in markdown_payload["content"]
    assert "Outlier billing concentration" in markdown_payload["content"]
    assert "Originating alert evidence." in markdown_payload["content"]
    assert "Origin claim source" in markdown_payload["content"]
    assert "evidence-001#source:0" in markdown_payload["content"]
    assert "/knowledgebases/kb-1/documents/source-doc/preview" in markdown_payload["content"]
    assert "Evidence is ready for supervisor review." in markdown_payload["content"]
    assert "## Audit Trail" in markdown_payload["content"]
    assert "case.feedback.create" in markdown_payload["content"]
    assert "case.promote" in markdown_payload["content"]

    exported_json = client.get(
        f"/cases/{case_id}/dossier/export",
        params={**kb, "format": "json"},
    )
    assert exported_json.status_code == 200
    json_payload = exported_json.json()
    assert json_payload["filename"] == f"case-{case_id}.json"
    exported_content = json.loads(json_payload["content"])
    assert exported_content["case"]["id"] == case_id
    assert exported_content["evidence_packs"][0]["provenance"][0]["label"] == (
        "Origin claim source"
    )
    assert [event["action"] for event in exported_content["audit_events"]] == [
        "case.feedback.create",
        "case.promote",
    ]
    assert "Evidence is ready for supervisor review." not in json.dumps(
        exported_content["audit_events"]
    )


def test_case_dossier_includes_explanation_review_status_without_raw_comments() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put(
        "kb-1",
        _evidence_pack(
            "evidence-001",
            alert_id="alert-001",
            reasoning="Originating alert evidence.",
            provenance_label="Origin claim source",
        ),
    )
    review_service = ExplanationReviewService(InMemoryExplanationReviewRepository())
    review_service.record_review(
        ExplanationReviewCreate(
            knowledge_base_id="kb-1",
            evidence_pack_id="evidence-001",
            target=ExplanationReviewTarget(
                target_type="narrative",
                target_id="narrative",
            ),
            state="unsupported",
            reasons=["missing_source"],
            actor_user_id="analyst-42",
            actor_email="analyst42@example.test",
            comment="SECRET beneficiary note 123-45-6789",
        )
    )
    client = _client_with_alert_history(
        evidence_repository=evidence_repository,
        review_service=review_service,
    )
    kb = {"knowledge_base_id": "kb-1"}
    promoted = client.post("/cases/promote", params=kb, json={"alert_id": "alert-001"})
    assert promoted.status_code == 200
    case_id = promoted.json()["case"]["id"]

    dossier = client.get(f"/cases/{case_id}/dossier", params=kb)

    assert dossier.status_code == 200
    payload = dossier.json()
    assert payload["explanation_review_summaries"] == [
        {
            "evidence_pack_id": "evidence-001",
            "review_id": payload["explanation_review_summaries"][0]["review_id"],
            "target": {"target_type": "narrative", "target_id": "narrative"},
            "state": "unsupported",
            "reason_count": 1,
            "updated_at": payload["explanation_review_summaries"][0]["updated_at"],
        }
    ]
    assert "SECRET beneficiary note" not in json.dumps(payload)

    markdown = client.get(
        f"/cases/{case_id}/dossier/export",
        params={**kb, "format": "markdown"},
    )
    assert markdown.status_code == 200
    markdown_content = markdown.json()["content"]
    assert "## Explanation Reviews" in markdown_content
    assert "evidence-001 narrative:narrative - unsupported (1 reason)" in markdown_content
    assert "SECRET beneficiary note" not in markdown_content


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
