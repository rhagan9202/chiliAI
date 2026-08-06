from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from analytics.explainability.adapters.evidence_in_memory import InMemoryEvidencePackRepository
from analytics.explainability.reviews import (
    ExplanationReviewService,
    InMemoryExplanationReviewRepository,
)
from api.app import create_app
from api.dependencies import get_domain_config, get_evidence_pack_repository
from api.middleware.auth import User, get_current_user
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEventQuery
from auditlog.service import AuditLogService
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig
from shared.types import EvidencePack

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


def _auth_enabled_config() -> DomainConfig:
    base = load_config(MEDICARE_YAML)
    return base.model_copy(update={"auth": AuthConfig(enabled=True)})


def _pack(evidence_pack_id: str, *, alert_id: str = "alert-1") -> EvidencePack:
    return EvidencePack(
        id=evidence_pack_id,
        alert_id=alert_id,
        reasoning="Provider billing concentration and upcoding indicate elevated fraud risk.",
        subgraph_nodes=["provider-1"],
        subgraph_edges=[],
        confidence=0.91,
    )


def _client(
    *,
    evidence_repository: InMemoryEvidencePackRepository | None = None,
    review_service: ExplanationReviewService | None = None,
    audit_service: AuditLogService | None = None,
    user: User | None = None,
    auth_enabled: bool = False,
) -> TestClient:
    app = create_app()
    if evidence_repository is not None:
        app.dependency_overrides[get_evidence_pack_repository] = lambda: evidence_repository
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    if auth_enabled:
        app.dependency_overrides[get_domain_config] = _auth_enabled_config
    if review_service is not None:
        app.state.explanation_review_service = review_service
    if audit_service is not None:
        app.state.audit_log_service = audit_service
    return TestClient(app)


def _review_payload(
    *,
    state: str = "unsupported",
    reasons: list[str] | None = None,
    comment: str | None = "This explanation repeats a sensitive analyst note.",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "target": {"target_type": "narrative", "target_id": "summary"},
        "state": state,
        "reasons": reasons if reasons is not None else ["unsupported_claim"],
    }
    if comment is not None:
        payload["comment"] = comment
    return payload


def test_create_and_list_evidence_review_records_sanitized_audit_event() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put("kb-1", _pack("evidence-1"))
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    review_service = ExplanationReviewService(InMemoryExplanationReviewRepository())
    client = _client(
        evidence_repository=evidence_repository,
        review_service=review_service,
        audit_service=audit_service,
        user=User(user_id="analyst-42", roles=["analyst"], email="analyst42@example.test"),
    )

    response = client.post(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
        json=_review_payload(comment="  This explanation repeats a sensitive analyst note.  "),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["knowledge_base_id"] == "kb-1"
    assert payload["evidence_pack_id"] == "evidence-1"
    assert payload["state"] == "unsupported"
    assert payload["reasons"] == ["unsupported_claim"]
    assert payload["comment"] == "This explanation repeats a sensitive analyst note."
    assert payload["actor_user_id"] == "analyst-42"
    assert payload["actor_email"] == "analyst42@example.test"
    assert payload["update_count"] == 0

    list_response = client.get(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["knowledge_base_id"] == "kb-1"
    assert listed["evidence_pack_id"] == "evidence-1"
    assert listed["page"] == {"page": 1, "page_size": 50, "total_items": 1}
    assert [item["id"] for item in listed["items"]] == [payload["id"]]

    audit_page = audit_service.list_events(
        AuditEventQuery(
            knowledge_base_id="kb-1",
            action_prefix="explanation.review.",
        )
    )
    assert [event.action for event in audit_page.items] == ["explanation.review.create"]
    event = audit_page.items[0]
    assert event.resource_type == "evidence_pack"
    assert event.resource_id == "evidence-1"
    assert event.actor_user_id == "analyst-42"
    assert event.after == {
        "state": "unsupported",
        "target_type": "narrative",
        "target_id": "summary",
        "reason_count": 1,
        "comment_present": True,
    }
    serialized_event = event.model_dump_json()
    assert "This explanation repeats a sensitive analyst note." not in serialized_event


def test_updating_evidence_review_records_update_audit_event() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put("kb-1", _pack("evidence-1"))
    audit_service = AuditLogService(InMemoryAuditLogRepository())
    review_service = ExplanationReviewService(InMemoryExplanationReviewRepository())
    client = _client(
        evidence_repository=evidence_repository,
        review_service=review_service,
        audit_service=audit_service,
        user=User(user_id="analyst-42", roles=["analyst"], email="analyst42@example.test"),
    )

    created = client.post(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
        json=_review_payload(state="useful", reasons=[], comment=None),
    )
    updated = client.post(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
        json=_review_payload(state="misleading", reasons=["wrong_peer_group"], comment=None),
    )

    assert created.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["update_count"] == 1
    audit_page = audit_service.list_events(
        AuditEventQuery(
            knowledge_base_id="kb-1",
            action_prefix="explanation.review.",
        )
    )
    assert [event.action for event in audit_page.items] == [
        "explanation.review.update",
        "explanation.review.create",
    ]


def test_evidence_review_negative_state_requires_reason_codes() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put("kb-1", _pack("evidence-1"))
    client = _client(evidence_repository=evidence_repository)

    response = client.post(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
        json=_review_payload(reasons=[]),
    )

    assert response.status_code == 422
    assert "reason" in response.text


def test_evidence_review_routes_do_not_cross_knowledge_base_scope() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put("kb-1", _pack("evidence-1", alert_id="alert-kb-1"))
    evidence_repository.put("kb-2", _pack("evidence-1", alert_id="alert-kb-2"))
    client = _client(evidence_repository=evidence_repository)

    create_response = client.post(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
        json=_review_payload(state="useful", reasons=[], comment=None),
    )
    kb_2_response = client.get(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-2"},
    )

    assert create_response.status_code == 200
    assert kb_2_response.status_code == 200
    assert kb_2_response.json()["items"] == []
    assert kb_2_response.json()["page"]["total_items"] == 0


def test_evidence_review_route_returns_404_for_missing_evidence_pack() -> None:
    client = _client(evidence_repository=InMemoryEvidencePackRepository())

    post_response = client.post(
        "/evidence-packs/missing/reviews",
        params={"knowledge_base_id": "kb-1"},
        json=_review_payload(),
    )
    get_response = client.get(
        "/evidence-packs/missing/reviews",
        params={"knowledge_base_id": "kb-1"},
    )

    assert post_response.status_code == 404
    assert get_response.status_code == 404


def test_evidence_review_create_requires_analyst_when_auth_enabled() -> None:
    evidence_repository = InMemoryEvidencePackRepository()
    evidence_repository.put("kb-1", _pack("evidence-1"))
    client = _client(
        evidence_repository=evidence_repository,
        auth_enabled=True,
        user=User(user_id="viewer-1", roles=["viewer"]),
    )

    read_response = client.get(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
    )
    write_response = client.post(
        "/evidence-packs/evidence-1/reviews",
        params={"knowledge_base_id": "kb-1"},
        json=_review_payload(state="useful", reasons=[], comment=None),
    )

    assert read_response.status_code == 200
    assert write_response.status_code == 403
