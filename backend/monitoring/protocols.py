"""Service-level protocols for the monitoring module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from monitoring.service_models import MonitoringEvaluationRequest, MonitoringEvaluationResponse


@runtime_checkable
class MonitoringServiceProtocol(Protocol):
    """Service boundary for active monitoring evaluation."""

    def evaluate(self, request: MonitoringEvaluationRequest) -> MonitoringEvaluationResponse: ...


__all__ = [
    "MonitoringServiceProtocol",
]