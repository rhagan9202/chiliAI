"""Public exports for the monitoring module."""

from __future__ import annotations

from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.adapters.protocols import ObservationSourceProtocol
from monitoring.exceptions import MonitoringConfigurationError, MonitoringError, MonitoringSourceError
from monitoring.models import AlertCandidate, MonitoringBatch, MonitoringObservation
from monitoring.protocols import MonitoringServiceProtocol
from monitoring.service import MonitoringService, create_monitoring_service
from monitoring.service_models import MonitoringEvaluationRequest, MonitoringEvaluationResponse

__all__ = [
    "AlertCandidate",
    "InMemoryObservationSource",
    "MonitoringBatch",
    "MonitoringConfigurationError",
    "MonitoringError",
    "MonitoringEvaluationRequest",
    "MonitoringEvaluationResponse",
    "MonitoringObservation",
    "MonitoringService",
    "MonitoringServiceProtocol",
    "MonitoringSourceError",
    "ObservationSourceProtocol",
    "create_monitoring_service",
]