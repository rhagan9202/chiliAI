"""Shared alert lifecycle rules."""

from __future__ import annotations

from typing import Literal, get_args

from monitoring.exceptions import AlertLifecycleError

AlertStatus = Literal["open", "acknowledged", "investigating", "resolved", "dismissed"]

VALID_ALERT_STATUSES: frozenset[str] = frozenset(get_args(AlertStatus))

ALERT_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"acknowledged", "dismissed"}),
    "acknowledged": frozenset({"investigating", "open"}),
    "investigating": frozenset({"resolved", "dismissed", "open"}),
    "resolved": frozenset({"open"}),
    "dismissed": frozenset({"open"}),
}


def validate_alert_transition(current_status: str, new_status: str) -> None:
    """Raise when the requested alert lifecycle transition is not permitted."""

    if new_status not in VALID_ALERT_STATUSES:
        raise AlertLifecycleError(current_status, new_status)
    if new_status == current_status:
        return
    allowed = ALERT_TRANSITIONS.get(current_status, frozenset())
    if new_status not in allowed:
        raise AlertLifecycleError(current_status, new_status)


__all__ = [
    "ALERT_TRANSITIONS",
    "AlertStatus",
    "VALID_ALERT_STATUSES",
    "validate_alert_transition",
]
