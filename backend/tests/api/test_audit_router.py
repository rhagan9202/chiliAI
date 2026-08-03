"""Tests for the SAFE-CMS-009 audit ledger query router."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_domain_config
from api.middleware.auth import User, get_current_user
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEvent, AuditEventCreate
from auditlog.service import AuditLogService
from config.loader import load_config
from config.schema import AuthConfig, DomainConfig

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"
MEDICARE_YAML = DEFAULTS_DIR / "medicare_fraud.yaml"


def _event(
    action: str,
    *,
    occurred_at: datetime,
    tenant_id: str = "tenant-1",
    knowledge_base_id: str | None = "kb-1",
    actor_user_id: str = "analyst-1",
    resource_type: str = "case",
    resource_id: str = "case-1",
) -> AuditEventCreate:
    return AuditEventCreate(
        tenant_id=tenant_id,
        knowledge_base_id=knowledge_base_id,
        occurred_at=occurred_at,
        actor_user_id=actor_user_id,
        actor_email="analyst@example.test",
        actor_roles=["analyst"],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before={"status": "open"},
        after={"status": "in_review"},
        correlation_id="corr-1",
        outcome="success",
        metadata={"source": "test"},
    )


def _auth_enabled_config() -> DomainConfig:
    base = load_config(MEDICARE_YAML)
    return base.model_copy(update={"auth": AuthConfig(enabled=True)})


class _FailingAuditRepository(InMemoryAuditLogRepository):
    def append(self, event: AuditEvent) -> None:
        raise RuntimeError("audit sink unavailable")


def test_audit_events_route_returns_empty_page() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/audit/events", params={"tenant_id": "tenant-1"})

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": {"page": 1, "page_size": 50, "total_items": 0},
    }


def test_audit_events_filter_scope_time_range_and_paginate() -> None:
    app = create_app()
    service = AuditLogService(InMemoryAuditLogRepository())
    base = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    service.record(_event("case.update", occurred_at=base, resource_id="case-1"))
    service.record(
        _event("case.feedback", occurred_at=base + timedelta(minutes=1), resource_id="case-2")
    )
    service.record(
        _event(
            "case.update",
            occurred_at=base + timedelta(minutes=2),
            knowledge_base_id="kb-2",
            resource_id="case-3",
        )
    )
    service.record(
        _event(
            "alert.ack",
            occurred_at=base + timedelta(minutes=3),
            resource_type="alert",
            resource_id="alert-1",
        )
    )
    app.state.audit_log_service = service

    with TestClient(app) as client:
        response = client.get(
            "/audit/events",
            params={
                "tenant_id": "tenant-1",
                "knowledge_base_id": "kb-1",
                "action_prefix": "case.",
                "from": (base + timedelta(seconds=30)).isoformat(),
                "to": (base + timedelta(minutes=1, seconds=1)).isoformat(),
                "limit": 1,
                "offset": 0,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == {"page": 1, "page_size": 1, "total_items": 1}
    assert [event["resource_id"] for event in payload["items"]] == ["case-2"]
    assert payload["items"][0]["before"] == {"status": "open"}
    assert payload["items"][0]["after"] == {"status": "in_review"}


def test_audit_events_requires_admin_when_auth_enabled() -> None:
    app = create_app()
    app.dependency_overrides[get_domain_config] = _auth_enabled_config
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="viewer-1", roles=["viewer"]
    )

    with TestClient(app) as client:
        response = client.get("/audit/events", params={"tenant_id": "tenant-1"})

    assert response.status_code == 403


def test_audit_status_exposes_write_failure_buffer() -> None:
    app = create_app()
    service = AuditLogService(_FailingAuditRepository())
    service.record(
        _event(
            "case.update",
            occurred_at=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
        )
    )
    app.state.audit_log_service = service

    with TestClient(app) as client:
        response = client.get("/audit/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["failed_write_count"] == 1
    assert len(payload["recent_write_failures"]) == 1
    failure = payload["recent_write_failures"][0]
    assert failure["action"] == "case.update"
    assert failure["resource_type"] == "case"
    assert failure["resource_id"] == "case-1"
    assert failure["error_class"] == "RuntimeError"
    assert failure["error_message"] == "audit sink unavailable"
