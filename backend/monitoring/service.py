"""Service entry point for active monitoring evaluation flows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, get_args

from monitoring.adapters.in_memory import InMemoryAlertRepository
from monitoring.adapters.protocols import ObservationSourceProtocol
from monitoring.exceptions import (
    AlertAlreadyResolvedError,
    AlertLifecycleError,
    AlertNotFoundError,
    MonitoringConfigurationError,
    MonitoringSourceError,
)
from monitoring.models import (
    AlertCandidate,
    AlertGroup,
    MonitoringObservation,
    SuppressionRule,
)
from monitoring.service_models import (
    AlertListRequest,
    AlertListResponse,
    MonitoringEvaluationRequest,
    MonitoringEvaluationResponse,
    ResolutionRequest,
)
from events.protocols import EventBus
from events.types import AlertCreatedReference, AlertsCreatedEvent
from shared.types import Alert
from shared.utils import generate_id, utc_now


_AlertStatus = Literal[
    "open", "acknowledged", "investigating", "resolved", "dismissed"
]
_VALID_ALERT_STATUSES: frozenset[str] = frozenset(get_args(_AlertStatus))

# Severity ordering used for rate-limit prioritization (highest first).
_SEVERITY_ORDER: dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

# Lifecycle state machine — additional "any -> open" reopen edge enforced separately.
ALERT_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"acknowledged", "dismissed"}),
    "acknowledged": frozenset({"investigating", "open"}),
    "investigating": frozenset({"resolved", "dismissed", "open"}),
    "resolved": frozenset({"open"}),
    "dismissed": frozenset({"open"}),
}


class MonitoringService:
    """Coordinate monitoring batch loading, threshold evaluation, and alert publication."""

    def __init__(
        self,
        observation_source: ObservationSourceProtocol,
        *,
        event_bus: EventBus,
        dedup_window_seconds: int = 3600,
        max_alerts_per_evaluation: int = 100,
        suppression_rules: list[SuppressionRule] | None = None,
        grouping_window_seconds: int = 300,
    ) -> None:
        self._observation_source = observation_source
        self._event_bus = event_bus
        self._dedup_window_seconds = dedup_window_seconds
        self._max_alerts_per_evaluation = max_alerts_per_evaluation
        self._suppression_rules: list[SuppressionRule] = list(suppression_rules or [])
        self._grouping_window_seconds = grouping_window_seconds
        self._dedup_index: dict[tuple[str, str], datetime] = {}

    @property
    def suppression_rules(self) -> list[SuppressionRule]:
        return list(self._suppression_rules)

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

        now = utc_now()
        observations = list(batch.observations)
        processed_count = len(observations)

        # E8-S03: filter out observations matched by suppression rules.
        suppressed_by_rule_count = 0
        post_rule_observations: list[MonitoringObservation] = []
        for observation in observations:
            if self._is_suppressed_by_rule(observation, now=now):
                suppressed_by_rule_count += 1
                continue
            post_rule_observations.append(observation)

        # E8-S01: filter to the rolling window before threshold + min-observation checks.
        window_start = now - timedelta(minutes=request.window_minutes)
        in_window = [
            observation
            for observation in post_rule_observations
            if observation.observed_at >= window_start
        ]

        # Group in-window observations by (entity_id, metric_name) so we can enforce
        # min_observations_in_window before generating any alert candidate.
        grouped: dict[tuple[str, str], list[MonitoringObservation]] = {}
        for observation in in_window:
            grouped.setdefault((observation.entity_id, observation.metric_name), []).append(
                observation
            )

        candidates: list[AlertCandidate] = []
        for (_entity_id, _metric_name), bucket in grouped.items():
            exceeders = [
                observation
                for observation in bucket
                if observation.score >= request.medium_threshold
            ]
            if len(exceeders) < request.min_observations_in_window:
                continue
            # Use the highest-scoring observation as the candidate's source.
            top = max(exceeders, key=lambda observation: observation.score)
            candidates.append(
                _to_alert_candidate(
                    top,
                    medium_threshold=request.medium_threshold,
                    high_threshold=request.high_threshold,
                )
            )

        # E8-S02: apply deduplication.
        deduped: list[AlertCandidate] = []
        suppressed_count = 0
        dedup_window = timedelta(seconds=self._dedup_window_seconds)
        for candidate in candidates:
            key = (candidate.entity_id, candidate.metric_name)
            previous = self._dedup_index.get(key)
            if previous is not None and (now - previous) < dedup_window:
                suppressed_count += 1
                continue
            self._dedup_index[key] = now
            deduped.append(candidate)

        # E8-S04: apply rate limiting after dedup.
        deduped.sort(
            key=lambda candidate: (
                -_SEVERITY_ORDER.get(candidate.severity, 0),
                -candidate.score,
            )
        )
        rate_limited_count = 0
        if len(deduped) > self._max_alerts_per_evaluation:
            rate_limited_count = len(deduped) - self._max_alerts_per_evaluation
            deduped = deduped[: self._max_alerts_per_evaluation]

        alerts = [_to_alert(candidate, created_at=now) for candidate in deduped]

        # E8-S06: cluster alerts by entity_type within the configured time tolerance.
        alert_groups = _build_alert_groups(
            alerts, tolerance_seconds=self._grouping_window_seconds, now=now
        )

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
            processed_observation_count=processed_count,
            alert_count=len(alerts),
            alerts=alerts,
            suppressed_count=suppressed_count,
            suppressed_by_rule_count=suppressed_by_rule_count,
            rate_limited_count=rate_limited_count,
            alert_groups=alert_groups,
        )

    def _is_suppressed_by_rule(
        self,
        observation: MonitoringObservation,
        *,
        now: datetime,
    ) -> bool:
        for rule in self._suppression_rules:
            if rule.matches(
                entity_type=observation.entity_type,
                metric_name=observation.metric_name,
                now=now,
            ):
                return True
        return False


def create_monitoring_service(
    observation_source: ObservationSourceProtocol,
    *,
    event_bus: EventBus,
    dedup_window_seconds: int = 3600,
    max_alerts_per_evaluation: int = 100,
    suppression_rules: list[SuppressionRule] | None = None,
    grouping_window_seconds: int = 300,
) -> MonitoringService:
    """Create the default monitoring service."""

    return MonitoringService(
        observation_source,
        event_bus=event_bus,
        dedup_window_seconds=dedup_window_seconds,
        max_alerts_per_evaluation=max_alerts_per_evaluation,
        suppression_rules=suppression_rules,
        grouping_window_seconds=grouping_window_seconds,
    )


def transition_alert_status(
    alert: Alert,
    new_status: str,
    actor: str,
    *,
    resolution_notes: str | None = None,
) -> Alert:
    """Return a copy of ``alert`` after applying a valid lifecycle transition."""

    if new_status not in _VALID_ALERT_STATUSES:
        raise AlertLifecycleError(alert.status, new_status)

    current = alert.status
    if new_status != current:
        allowed = ALERT_TRANSITIONS.get(current, frozenset())
        if new_status not in allowed:
            raise AlertLifecycleError(current, new_status)

    update: dict[str, object] = {
        "status": new_status,
        "updated_at": utc_now(),
    }
    if new_status == "acknowledged":
        update["acknowledged"] = True
    elif new_status == "open":
        update["acknowledged"] = False
        update["resolved_by"] = None
        update["resolution_notes"] = None
    elif new_status == "resolved":
        update["resolved_by"] = actor
        if resolution_notes is not None:
            update["resolution_notes"] = resolution_notes
    return alert.model_copy(update=update)


class AlertsService:
    """Manage alert listing and lifecycle transitions over an alert repository."""

    def __init__(self, repository: InMemoryAlertRepository) -> None:
        self._repository = repository

    def list_alerts(self, request: AlertListRequest) -> AlertListResponse:
        matches = [alert for alert in self._repository.all() if _matches(alert, request)]
        page = matches[request.offset : request.offset + request.limit]
        return AlertListResponse(items=page, total=len(matches))

    def acknowledge_alert(self, alert_id: str) -> Alert:
        alert = self._repository.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id)
        if alert.status == "resolved":
            raise AlertAlreadyResolvedError(alert_id)
        # Re-route through the lifecycle state machine when the source state allows it
        # (open -> acknowledged); otherwise fall back to the legacy direct update so
        # E5-S01 callers that acknowledge an already-acknowledged alert keep working.
        try:
            updated = transition_alert_status(alert, "acknowledged", actor="system")
        except AlertLifecycleError:
            updated = alert.model_copy(
                update={
                    "status": "acknowledged",
                    "acknowledged": True,
                    "updated_at": utc_now(),
                }
            )
        self._repository.put(updated)
        return updated

    def resolve_alert(self, alert_id: str, request: ResolutionRequest) -> Alert:
        alert = self._repository.get(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id)
        if alert.status == "resolved":
            raise AlertAlreadyResolvedError(alert_id)
        # Retain backward-compatible direct update — E5-S02 allows resolving from
        # any non-resolved state, including "open".
        updated = alert.model_copy(
            update={
                "status": "resolved",
                "resolved_by": request.resolved_by,
                "resolution_notes": request.notes,
                "updated_at": utc_now(),
            }
        )
        self._repository.put(updated)
        return updated


def create_alerts_service(repository: InMemoryAlertRepository) -> AlertsService:
    """Create the default alerts service from an in-memory repository."""

    return AlertsService(repository)


def _matches(alert: Alert, request: AlertListRequest) -> bool:
    if request.severity is not None and alert.severity != request.severity:
        return False
    if request.entity_type is not None and alert.entity_type != request.entity_type:
        return False
    if request.status is not None and alert.status != request.status:
        return False
    return True


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
        metric_name=observation.metric_name,
        evidence_pack_id=observation.evidence_pack_id,
    )


def _to_alert(candidate: AlertCandidate, *, created_at: datetime) -> Alert:
    return Alert(
        id=generate_id(),
        entity_type=candidate.entity_type,
        entity_id=candidate.entity_id,
        severity=candidate.severity,
        title=candidate.title,
        reasoning=candidate.reasoning,
        evidence_pack_id=candidate.evidence_pack_id,
        created_at=created_at,
    )


def _build_alert_groups(
    alerts: list[Alert],
    *,
    tolerance_seconds: int,
    now: datetime,
) -> list[AlertGroup]:
    """Cluster alerts sharing entity_type within the time tolerance into groups."""

    if len(alerts) < 2:
        return []
    by_entity_type: dict[str, list[Alert]] = {}
    for alert in alerts:
        by_entity_type.setdefault(alert.entity_type, []).append(alert)
    groups: list[AlertGroup] = []
    tolerance = timedelta(seconds=tolerance_seconds)
    for entity_type, bucket in by_entity_type.items():
        if len(bucket) < 2:
            continue
        bucket.sort(key=lambda alert: alert.created_at)
        anchor_time = bucket[0].created_at
        if all(alert.created_at - anchor_time <= tolerance for alert in bucket):
            groups.append(
                AlertGroup(
                    group_id=generate_id(),
                    alert_ids=[alert.id for alert in bucket],
                    entity_type=entity_type,
                    created_at=now,
                    correlation_reason=(
                        f"Same entity_type '{entity_type}' within {tolerance_seconds}s window"
                    ),
                )
            )
    return groups


__all__ = [
    "ALERT_TRANSITIONS",
    "AlertsService",
    "MonitoringService",
    "create_alerts_service",
    "create_monitoring_service",
    "transition_alert_status",
]
