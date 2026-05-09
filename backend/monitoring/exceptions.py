"""Exception hierarchy for the monitoring module."""

from __future__ import annotations


class MonitoringError(Exception):
    """Base exception for monitoring module failures."""


class MonitoringConfigurationError(MonitoringError):
    """Raised when a monitoring request is invalid or incomplete."""


class MonitoringSourceError(MonitoringError):
    """Raised when the configured observation source cannot return monitoring data."""


class AlertNotFoundError(MonitoringError):
    """Raised when an alert lookup targets an unknown alert id."""

    def __init__(self, alert_id: str) -> None:
        super().__init__(f"Alert '{alert_id}' was not found.")
        self.alert_id = alert_id


class AlertAlreadyResolvedError(MonitoringError):
    """Raised when a resolution is attempted on an already-resolved alert."""

    def __init__(self, alert_id: str) -> None:
        super().__init__(f"Alert '{alert_id}' is already resolved.")
        self.alert_id = alert_id


class AlertLifecycleError(MonitoringError):
    """Raised when an alert status transition violates the lifecycle state machine."""

    def __init__(self, current_status: str, new_status: str) -> None:
        super().__init__(
            f"Invalid alert lifecycle transition: '{current_status}' -> '{new_status}'."
        )
        self.current_status = current_status
        self.new_status = new_status


__all__ = [
    "AlertAlreadyResolvedError",
    "AlertLifecycleError",
    "AlertNotFoundError",
    "MonitoringConfigurationError",
    "MonitoringError",
    "MonitoringSourceError",
]
