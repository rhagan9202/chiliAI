"""Protocols for audit ledger storage."""

from __future__ import annotations

from typing import Protocol

from auditlog.models import AuditEvent, AuditEventPage, AuditEventQuery


class AuditLogRepository(Protocol):
    """Append-only repository for audit events."""

    def append(self, event: AuditEvent) -> None:
        """Append a new event to the ledger."""
        ...

    def list(self, query: AuditEventQuery) -> AuditEventPage:
        """Return a filtered, newest-first page of events."""
        ...
