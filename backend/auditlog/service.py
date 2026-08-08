"""Audit ledger service."""

from __future__ import annotations

from auditlog.models import (
    AuditEvent,
    AuditEventCreate,
    AuditEventPage,
    AuditEventQuery,
    AuditWriteFailure,
)
from auditlog.protocols import AuditLogRepository
from shared.metrics import chili_audit_write_failures_total
from shared.utils import generate_id, utc_now


class AuditLogService:
    """Append and query audit events while isolating write failures."""

    def __init__(
        self,
        repository: AuditLogRepository,
        *,
        max_failure_buffer: int = 100,
    ) -> None:
        self._repository = repository
        self._max_failure_buffer = max_failure_buffer
        self._write_failures: list[AuditWriteFailure] = []

    @property
    def failed_write_count(self) -> int:
        return len(self._write_failures)

    @property
    def write_failures(self) -> list[AuditWriteFailure]:
        return [failure.model_copy(deep=True) for failure in self._write_failures]

    def record(self, payload: AuditEventCreate) -> AuditEvent | None:
        event = AuditEvent(
            event_id=generate_id(),
            occurred_at=payload.occurred_at or utc_now(),
            tenant_id=payload.tenant_id,
            knowledge_base_id=payload.knowledge_base_id,
            actor_user_id=payload.actor_user_id,
            actor_email=payload.actor_email,
            actor_roles=list(payload.actor_roles),
            action=payload.action,
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            before=payload.before,
            after=payload.after,
            correlation_id=payload.correlation_id,
            client_ip=payload.client_ip,
            user_agent=payload.user_agent,
            outcome=payload.outcome,
            failure_reason=payload.failure_reason,
            metadata=dict(payload.metadata),
        )
        try:
            self._repository.append(event)
        except Exception as exc:  # noqa: BLE001 - audit failures must not corrupt the primary flow.
            self._capture_write_failure(event, exc)
            return None
        return event

    def list_events(self, query: AuditEventQuery) -> AuditEventPage:
        return self._repository.list(query)

    def _capture_write_failure(self, event: AuditEvent, exc: Exception) -> None:
        chili_audit_write_failures_total.labels(
            action=event.action, error_class=exc.__class__.__name__
        ).inc()
        failure = AuditWriteFailure(
            occurred_at=utc_now(),
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            error_class=exc.__class__.__name__,
            error_message=str(exc),
        )
        self._write_failures.append(failure)
        if len(self._write_failures) > self._max_failure_buffer:
            self._write_failures = self._write_failures[-self._max_failure_buffer :]
