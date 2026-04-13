"""Service-level protocols for the monitoring module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from monitoring.service_models import MonitoringEvaluationRequest, MonitoringEvaluationResponse


@runtime_checkable
class MonitoringServiceProtocol(Protocol):
    """Service boundary for active monitoring evaluation."""

    # TODO(production): Add async/streaming methods for continuous monitoring:
    # - evaluate_async(request) -> Awaitable[MonitoringEvaluationResponse]
    # - list_active_alerts(kb_id) -> list[Alert]
    # - acknowledge_alert(alert_id) -> None
    # - suppress_alerts(rule: SuppressionRule) -> None

    def evaluate(self, request: MonitoringEvaluationRequest) -> MonitoringEvaluationResponse: ...


__all__ = [
    "MonitoringServiceProtocol",
]