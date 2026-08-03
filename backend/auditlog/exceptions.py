"""Exception hierarchy for the audit-log module."""

from __future__ import annotations


class AuditLogError(Exception):
    """Base exception for audit-log failures."""


class AuditLogPersistenceError(AuditLogError):
    """Raised when an audit event cannot be persisted or read back."""


__all__ = ["AuditLogError", "AuditLogPersistenceError"]
