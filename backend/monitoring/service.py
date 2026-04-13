"""Service entry point for active monitoring evaluation flows."""

from __future__ import annotations

from datetime import datetime, timezone

from monitoring.adapters.protocols import ObservationSourceProtocol
from monitoring.exceptions import MonitoringConfigurationError, MonitoringSourceError
from monitoring.models import AlertCandidate, MonitoringObservation
from monitoring.service_models import MonitoringEvaluationRequest, MonitoringEvaluationResponse
from events.protocols import EventBus
from events.types import AlertCreatedReference, AlertsCreatedEvent
from shared.types import Alert
from shared.utils import generate_id


class MonitoringService:
    """Coordinate monitoring batch loading, threshold evaluation, and alert publication."""

    # TODO(production): Replace simple threshold-based alerting with production
    # monitoring capabilities:
    # - Anomaly detection algorithms (z-score, isolation forest, historical baseline)
    # - Time-window aggregation ("N observations exceeding threshold in M minutes")
    # - Alert deduplication (same entity+metric within a configurable window = 1 alert)
    # - Alert suppression / maintenance windows
    # - Rate limiting to prevent alert storms on large datasets
    # - Entity-type-aware thresholds (configurable per entity type in DomainConfig)
    # - Alert grouping/correlation for related entities
    # Current implementation fires one alert per observation above threshold.

    def __init__(self, observation_source: ObservationSourceProtocol, *, event_bus: EventBus) -> None:
        self._observation_source = observation_source
        self._event_bus = event_bus

    def evaluate(self, request: MonitoringEvaluationRequest) -> MonitoringEvaluationResponse:
        try:
            batch = self._observation_source.load_batch(
                knowledge_base_id=request.knowledge_base_id,
                batch_id=request.batch_id,
            )
        except ValueError as exc:
            raise MonitoringConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise MonitoringSourceError("Failed to load monitoring batch.") from exc

        candidates = [
            _to_alert_candidate(
                observation,
                medium_threshold=request.medium_threshold,
                high_threshold=request.high_threshold,
            )
            for observation in batch.observations
            if observation.score >= request.medium_threshold
        ]
        alerts = [_to_alert(candidate) for candidate in candidates]
        if alerts:
            self._event_bus.publish(
                AlertsCreatedEvent(
                    alerts=[
                        AlertCreatedReference(
                            knowledge_base_id=request.knowledge_base_id,
                            alert_id=alert.id,
                            entity_id=alert.entity_id,
                            severity=alert.severity,
                            evidence_pack_id=alert.evidence_pack_id,
                        )
                        for alert in alerts
                    ]
                )
            )

        return MonitoringEvaluationResponse(
            knowledge_base_id=request.knowledge_base_id,
            batch_id=request.batch_id,
            processed_observation_count=len(batch.observations),
            alert_count=len(alerts),
            alerts=alerts,
        )


def create_monitoring_service(
    observation_source: ObservationSourceProtocol,
    *,
    event_bus: EventBus,
) -> MonitoringService:
    """Create the default monitoring service."""

    return MonitoringService(observation_source, event_bus=event_bus)


def _to_alert_candidate(
    observation: MonitoringObservation,
    *,
    medium_threshold: float,
    high_threshold: float,
) -> AlertCandidate:
    severity = "high" if observation.score >= high_threshold else "medium"
    return AlertCandidate(
        entity_id=observation.entity_id,
        entity_type=observation.entity_type,
        severity=severity,
        title=f"{observation.metric_name} threshold exceeded",
        reasoning=observation.rationale,
        score=observation.score,
        evidence_pack_id=observation.evidence_pack_id,
    )


def _to_alert(candidate: AlertCandidate) -> Alert:
    return Alert(
        id=generate_id(),
        entity_type=candidate.entity_type,
        entity_id=candidate.entity_id,
        severity=candidate.severity,
        title=candidate.title,
        reasoning=candidate.reasoning,
        evidence_pack_id=candidate.evidence_pack_id,
        created_at=datetime.now(timezone.utc),
    )


__all__ = ["MonitoringService", "create_monitoring_service"]