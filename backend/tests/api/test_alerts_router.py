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
from monitoring.exceptions import AlertConcurrentModificationError, MonitoringSourceError
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


class _StoreRaisingConcurrentModificationOn(InMemoryAlertHistoryWriter):
    """Alert store seeded with one open kb-1 alert whose transition always
    loses a write race.

    Simulates what both adapters now do for real under contention (a lost
    optimistic-concurrency race), without needing to actually run threads
    through the fix's lock/CAS guard -- that race itself is proven directly
    against ``InMemoryAlertHistoryWriter`` in
    ``tests/monitoring/test_alert_history_writer.py``. This class exists
    only to check what the router/gateway layer does with the typed
    exception once an adapter raises it.
    """

    def __init__(self, alert_id: str = "alert-1") -> None:
        super().__init__()
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
        raise AlertConcurrentModificationError(alert_id)


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


def _client_allowing_server_errors(
    *, store: AlertFeedStoreProtocol, audit: AuditLogService
) -> TestClient:
    """A client that turns a truly-unhandled exception into a 500 response.

    ``TestClient``'s default (``raise_server_exceptions=True``) re-raises an
    unhandled exception in the test process instead of returning a response,
    which makes "the route falls through as a 500" impossible to assert
    against directly. This variant lets that response actually form, so a
    pre-fix run can be shown returning 500 and a post-fix run 409 from the
    exact same client construction.
    """
    app = create_app()
    app.dependency_overrides[get_alert_feed_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: User(
        user_id="analyst-42",
        roles=["analyst"],
        email="analyst42@example.test",
    )
    app.state.audit_log_service = audit
    return TestClient(app, raise_server_exceptions=False)


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


def test_a_lost_write_race_surfaces_as_409_not_500() -> None:
    """A caller can retry a 409; it has no useful response to a bare 500.

    Before this task, ``AlertConcurrentModificationError`` did not exist and
    a lost race reached the caller exactly like a genuine outage: an
    unhandled exception (nothing in ``api.dependencies`` caught it), which
    Starlette's default error handling turns into an opaque 500 with no
    signal that retrying would likely succeed.
    """
    audit = RecordingAuditLogService()
    store = _StoreRaisingConcurrentModificationOn("alert-1")
    client = _client_allowing_server_errors(store=store, audit=audit)

    response = client.patch(
        "/alerts/alert-1/status",
        json={"knowledge_base_id": "kb-1", "status": "acknowledged"},
    )

    assert response.status_code == 409


class _StoreLosingRaceOn(InMemoryAlertHistoryWriter):
    """Alert store seeded with three open kb-1 alerts, one of which always
    loses a write race instead of transitioning.

    Sibling of ``_StoreFailingOn`` (a genuine persistence failure): this one
    raises the typed, always-safe-to-retry ``AlertConcurrentModificationError``
    instead of the generic ``MonitoringSourceError``, so the router/bulk
    builder's differing treatment of the two can be checked.
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
            raise AlertConcurrentModificationError(alert_id)
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


def test_a_lost_race_in_a_bulk_update_is_skipped_not_aborted() -> None:
    """Nothing commits on the lost-race branch, so skipping it is safe.

    Before this task the bulk endpoint aborted the whole batch on any
    ``MonitoringSourceError`` because a lost race and a genuine outage were
    the same untypeable exception. Now that a lost race is its own type,
    and both adapters raise it *before* writing anything, the affected row
    can be reported back as skipped (``reason="concurrent_modification"``)
    while the rest of the batch -- including alerts after it -- still goes
    through, rather than a real infrastructure outage's caller-visible
    behavior (a still-aborting 500) being applied to a benign, retryable
    per-row conflict.
    """
    audit = RecordingAuditLogService()
    store = _StoreLosingRaceOn("alert-2")
    client = _client(store=store, audit=audit)

    response = client.post(
        "/alerts/bulk/status",
        json={
            "knowledge_base_id": "kb-1",
            "alert_ids": ["alert-1", "alert-2", "alert-3"],
            "status": "acknowledged",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["updated_alerts"]] == ["alert-1", "alert-3"]
    assert body["rejected_alerts"] == [
        {"alert_id": "alert-2", "reason": "concurrent_modification"}
    ]
    audited = {e.resource_id for e in audit.events}
    assert audited == {"alert-1", "alert-3"}
