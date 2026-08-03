from __future__ import annotations

from datetime import datetime, timedelta, timezone

from auditlog.adapters.in_memory import InMemoryAuditLogRepository
from auditlog.models import AuditEventCreate, AuditEventQuery
from auditlog.protocols import AuditLogRepository
from auditlog.service import AuditLogService


def _create_event(
    action: str,
    *,
    occurred_at: datetime | None = None,
    actor_user_id: str = "analyst-1",
    knowledge_base_id: str | None = "kb-1",
    resource_type: str = "case",
    resource_id: str = "case-1",
) -> AuditEventCreate:
    return AuditEventCreate(
        tenant_id="tenant-1",
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
        client_ip="127.0.0.1",
        user_agent="pytest",
        outcome="success",
        metadata={"case_title": "Redwood DME escalation"},
    )


def test_record_assigns_identity_and_lists_newest_first() -> None:
    service = AuditLogService(InMemoryAuditLogRepository())
    older = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    newer = older + timedelta(minutes=5)

    first = service.record(_create_event("case.update", occurred_at=older))
    second = service.record(_create_event("case.feedback", occurred_at=newer))

    assert first is not None
    assert second is not None
    assert first.event_id != second.event_id
    assert first.occurred_at == older
    page = service.list_events(AuditEventQuery(tenant_id="tenant-1"))
    assert [event.action for event in page.items] == ["case.feedback", "case.update"]
    assert page.total_items == 2
    assert page.limit == 50
    assert page.offset == 0


def test_query_filters_scope_resource_action_actor_outcome_and_time_window() -> None:
    service = AuditLogService(InMemoryAuditLogRepository())
    base = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    service.record(_create_event("case.update", occurred_at=base, resource_id="case-1"))
    service.record(
        _create_event(
            "alert.ack",
            occurred_at=base + timedelta(minutes=1),
            actor_user_id="analyst-2",
            resource_type="alert",
            resource_id="alert-1",
        )
    )
    service.record(
        _create_event(
            "case.update",
            occurred_at=base + timedelta(minutes=2),
            knowledge_base_id="kb-2",
            resource_id="case-2",
        )
    )

    page = service.list_events(
        AuditEventQuery(
            tenant_id="tenant-1",
            knowledge_base_id="kb-1",
            action_prefix="case.",
            actor_user_id="analyst-1",
            resource_type="case",
            resource_id="case-1",
            outcome="success",
            occurred_from=base - timedelta(seconds=1),
            occurred_to=base + timedelta(seconds=1),
        )
    )

    assert [event.resource_id for event in page.items] == ["case-1"]


def test_query_paginates_after_filtering() -> None:
    service = AuditLogService(InMemoryAuditLogRepository())
    base = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    for index in range(5):
        service.record(
            _create_event(
                "case.update",
                occurred_at=base + timedelta(minutes=index),
                resource_id=f"case-{index}",
            )
        )

    page = service.list_events(AuditEventQuery(tenant_id="tenant-1", limit=2, offset=1))

    assert [event.resource_id for event in page.items] == ["case-3", "case-2"]
    assert page.total_items == 5
    assert page.limit == 2
    assert page.offset == 1


def test_in_memory_repository_returns_defensive_copies() -> None:
    service = AuditLogService(InMemoryAuditLogRepository())
    event = service.record(_create_event("case.update"))
    assert event is not None

    page = service.list_events(AuditEventQuery(tenant_id="tenant-1"))
    page.items[0].after = {"status": "closed"}

    fresh = service.list_events(AuditEventQuery(tenant_id="tenant-1"))
    assert fresh.items[0].after == {"status": "in_review"}


class FailingRepository:
    def append(self, event):  # type: ignore[no-untyped-def]
        raise RuntimeError("disk full")

    def list(self, query):  # type: ignore[no-untyped-def]
        raise AssertionError("unused")


def test_record_captures_write_failures_without_raising() -> None:
    service = AuditLogService(FailingRepository())  # type: ignore[arg-type]

    recorded = service.record(_create_event("case.update"))

    assert recorded is None
    assert service.failed_write_count == 1
    assert service.write_failures[0].action == "case.update"
    assert service.write_failures[0].error_class == "RuntimeError"
    assert service.write_failures[0].error_message == "disk full"


def test_in_memory_repository_matches_protocol_shape() -> None:
    repository: AuditLogRepository = InMemoryAuditLogRepository()

    assert repository is not None
