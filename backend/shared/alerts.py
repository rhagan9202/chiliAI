"""Shared alert contract helpers."""

from __future__ import annotations

from typing import Literal, cast

AlertSeverity = Literal["low", "medium", "high", "critical"]

# Alert statuses treated as durably "active" across the alert feed, the SSE
# workspace snapshot, and the analytics-overview dashboard tile.
ACTIVE_ALERT_STATUSES = frozenset({"open", "acknowledged", "investigating"})


def normalize_severity(raw_severity: str, confidence: float) -> AlertSeverity:
    """Return a normalized analyst-facing alert severity."""

    severity = raw_severity.lower()
    if severity in {"low", "medium", "high", "critical"}:
        return cast(AlertSeverity, severity)
    if confidence >= 0.9:
        return "critical"
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


__all__ = ["ACTIVE_ALERT_STATUSES", "AlertSeverity", "normalize_severity"]
