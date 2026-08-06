"""In-memory audit ledger adapter for tests and local development."""

from __future__ import annotations

from auditlog.models import AuditEvent, AuditEventPage, AuditEventQuery


class InMemoryAuditLogRepository:
    """Append-only in-memory audit event repository."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self._events.append(event.model_copy(deep=True))

    def list(self, query: AuditEventQuery) -> AuditEventPage:
        events = [
            event.model_copy(deep=True)
            for event in self._events
            if _matches_query(event, query)
        ]
        events.sort(key=lambda event: (event.occurred_at, event.event_id), reverse=True)
        total_items = len(events)
        page = events[query.offset : query.offset + query.limit]
        return AuditEventPage(
            items=[event.model_copy(deep=True) for event in page],
            total_items=total_items,
            limit=query.limit,
            offset=query.offset,
        )


def _matches_query(event: AuditEvent, query: AuditEventQuery) -> bool:
    if query.tenant_id is not None and event.tenant_id != query.tenant_id:
        return False
    if query.knowledge_base_id is not None and event.knowledge_base_id != query.knowledge_base_id:
        return False
    if query.actor_user_id is not None and event.actor_user_id != query.actor_user_id:
        return False
    if query.action_prefix is not None and not event.action.startswith(query.action_prefix):
        return False
    if query.resource_type is not None and event.resource_type != query.resource_type:
        return False
    if query.resource_id is not None and event.resource_id != query.resource_id:
        return False
    if query.outcome is not None and event.outcome != query.outcome:
        return False
    if query.occurred_from is not None and event.occurred_at < query.occurred_from:
        return False
    if query.occurred_to is not None and event.occurred_at > query.occurred_to:
        return False
    return True
