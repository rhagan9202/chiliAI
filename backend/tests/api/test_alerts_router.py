"""Tests for the ``/alerts`` router's audit-on-mutation guarantees.

These focus on the bulk status-transition route: every alert it commits as
transitioned must land an ``audit_log`` row for that same transition, even
when a later alert in the batch fails. See ``AlertFeedStoreProtocol`` in
``monitoring/adapters/protocols.py`` for the durable store's per-call commit
semantics that make a mid-batch failure possible in the first place.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from api.dependencies import get_alert_feed_store
from api.middleware.auth import User, get_current_user
from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEvent, AuditEventQuery
from auditlog.service import AuditLogService
from monitoring.adapters.in_memory import InMemoryAlertHistoryWriter
from monitoring.adapters.protocols import AlertFeedStoreProtocol
from monitoring.exceptions import MonitoringSourceError
from monitoring.models import AlertHistoryRecord
from shared.utils import utc_now


class RecordingAuditLogService(AuditLogService):
    """Audit service backed by memory, exposing every recorded event."""

    def __init__(self) -> None:
        super().__init__(InMemoryAuditLogRepository())

    @property
    def events(self) -> list[AuditEvent]:
        return self.list_events(AuditEventQuery()).items


class _StoreFailingOn(InMemoryAlertHistoryWriter):
    """Alert store seeded with three open kb-1 alerts, one of which fails.

    ``transition_status`` raises ``MonitoringSourceError`` for the configured
    alert id and never touches this store's records for it -- mirroring the
    durable Postgres store, where a raise means that call's transition did
    not commit while every earlier successful call already has (each
    transition commits on its own pooled connection).
    """

    def __init__(self, fail_on: str) -> None:
        super().__init__()
        self._fail_on = fail_on
        self.transitioned_ids: list[str] = []
        created_at = utc_now()
        self.write_alerts(
            [
                AlertHistoryRecord(
                    knowledge_base_id="kb-1",
                    alert_id=alert_id,
                    entity_id=f"provider-{alert_id}",
                    entity_type="provider",
                    severity="high",
                    status="open",
                    title="Outlier billing concentration",
                    reasoning="Provider activity is materially above peers.",
                    metric_name="claims_per_week",
                    created_at=created_at,
                    updated_at=created_at,
                )
                for alert_id in ("alert-1", "alert-2", "alert-3")
            ]
        )

    def transition_status(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str,
        status: str,
        actor: str,
        reason: str | None = None,
    ) -> AlertHistoryRecord | None:
        if alert_id == self._fail_on:
            raise MonitoringSourceError("Failed to transition alert status.")
        updated = super().transition_status(
            alert_id,
            knowledge_base_id=knowledge_base_id,
            status=status,
            actor=actor,
            reason=reason,
        )
        if updated is not None:
            self.transitioned_ids.append(alert_id)
        return updated


def _client(*, store: AlertFeedStoreProtocol, audit: AuditLogService) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_alert_feed_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="analyst-42",
        roles=["analyst"],
        email="analyst42@example.test",
    )
    app.state.audit_log_service = audit
    return TestClient(app)


def test_a_failure_midway_through_a_bulk_update_leaves_no_unaudited_transition() -> None:
    """Each transition commits on its own connection.

    If alert 3 raises, alerts 1 and 2 are already committed, but the router's
    audit loop runs only after the whole batch -- so material state changes
    exist with no audit_log row. On a compliance-facing platform that is the
    part that matters.
    """
    audit = RecordingAuditLogService()
    store = _StoreFailingOn("alert-3")
    client = _client(store=store, audit=audit)

    response = client.post(
        "/alerts/bulk/status",
        json={
            "knowledge_base_id": "kb-1",
            "alert_ids": ["alert-1", "alert-2", "alert-3"],
            "status": "acknowledged",
        },
    )

    assert response.status_code == 500
    transitioned = store.transitioned_ids
    audited = {e.resource_id for e in audit.events}
    assert audited == set(transitioned), (
        f"committed {sorted(transitioned)} but audited {sorted(audited)}"
    )
