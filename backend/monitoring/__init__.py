"""Public exports for the monitoring module."""

from __future__ import annotations

from monitoring.adapters.in_memory import (
    InMemoryAlertRepository,
    InMemoryObservationSource,
    InMemoryObservationWriter,
)
from monitoring.adapters.protocols import ObservationSourceProtocol, ObservationWriter
from monitoring.exceptions import (
    AlertAlreadyResolvedError,
    AlertNotFoundError,
    MonitoringConfigurationError,
    MonitoringError,
    MonitoringSourceError,
)
from monitoring.models import AlertCandidate, MonitoringBatch, MonitoringObservation
from monitoring.protocols import AlertsServiceProtocol, MonitoringServiceProtocol
from monitoring.service import (
    AlertsService,
    MonitoringService,
    create_alerts_service,
    create_monitoring_service,
)
from monitoring.service_models import (
    AlertActionResponse,
    AlertListRequest,
    AlertListResponse,
    MonitoringEvaluationRequest,
    MonitoringEvaluationResponse,
    ResolutionRequest,
)

__all__ = [
    "AlertActionResponse",
    "AlertAlreadyResolvedError",
    "AlertCandidate",
    "AlertListRequest",
    "AlertListResponse",
    "AlertNotFoundError",
    "AlertsService",
    "AlertsServiceProtocol",
    "InMemoryAlertRepository",
    "InMemoryObservationSource",
    "InMemoryObservationWriter",
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
    "ObservationWriter",
    "ResolutionRequest",
    "create_alerts_service",
    "create_monitoring_service",
]