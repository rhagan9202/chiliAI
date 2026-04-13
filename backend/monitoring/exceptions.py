"""Exception hierarchy for the monitoring module."""

from __future__ import annotations


class MonitoringError(Exception):
    """Base exception for monitoring module failures."""


class MonitoringConfigurationError(MonitoringError):
    """Raised when a monitoring request is invalid or incomplete."""


class MonitoringSourceError(MonitoringError):
    """Raised when the configured observation source cannot return monitoring data."""


__all__ = [
    "MonitoringConfigurationError",
    "MonitoringError",
    "MonitoringSourceError",
]