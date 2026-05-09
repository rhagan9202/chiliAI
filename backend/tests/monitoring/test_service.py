"""Tests for the monitoring service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from monitoring.adapters.in_memory import InMemoryObservationSource
from monitoring.exceptions import (
    AlertLifecycleError,
    MonitoringConfigurationError,
    MonitoringSourceError,
)
from monitoring.models import (
    AlertGroup,
    MonitoringBatch,
    MonitoringObservation,
    SuppressionRule,
)
from monitoring.service import (
    MonitoringService,
    create_monitoring_service,
    transition_alert_status,
)
from monitoring.service_models import MonitoringEvaluationRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import AlertsCreatedEvent
from shared.types import Alert
from shared.utils import utc_now


def _observation(
    *,
    entity_id: str = "provider-7",
    entity_type: str = "provider",
    metric_name: str = "claim_volume",
    score: float = 0.92,
    rationale: str = "Threshold exceeded.",
    observed_at: datetime | None = None,
    evidence_pack_id: str | None = "pack-1",
) -> MonitoringObservation:
    return MonitoringObservation(
        entity_id=entity_id,
        entity_type=entity_type,
        metric_name=metric_name,
        score=score,
        rationale=rationale,
        observed_at=observed_at or utc_now(),
        evidence_pack_id=evidence_pack_id,
    )


def _build_service(
    observations: list[MonitoringObservation],
    *,
    dedup_window_seconds: int = 3600,
    max_alerts_per_evaluation: int = 100,
    suppression_rules: list[SuppressionRule] | None = None,
    grouping_window_seconds: int = 300,
) -> tuple[MonitoringService, InMemoryEventBus]:
    event_bus = InMemoryEventBus()
    source = InMemoryObservationSource(
        batches=[
            MonitoringBatch(
                knowledge_base_id="kb-1",
                batch_id="batch-1",
                observations=observations,
            )
        ]
    )
    service = create_monitoring_service(
        source,
        event_bus=event_bus,
        dedup_window_seconds=dedup_window_seconds,
        max_alerts_per_evaluation=max_alerts_per_evaluation,
        suppression_rules=suppression_rules,
        grouping_window_seconds=grouping_window_seconds,
    )
    return service, event_bus


def _request(**overrides: object) -> MonitoringEvaluationRequest:
    base: dict[str, object] = {
        "knowledge_base_id": "kb-1",
        "batch_id": "batch-1",
    }
    base.update(overrides)
    return MonitoringEvaluationRequest.model_validate(base)


def test_monitoring_service_generates_alerts_and_publishes_event() -> None:
    service, event_bus = _build_service(
        [
            _observation(score=0.92),
            _observation(entity_id="provider-8", score=0.55, evidence_pack_id=None),
        ]
    )

    response = service.evaluate(_request())

    assert response.processed_observation_count == 2
    assert response.alert_count == 1
    assert response.alerts[0].entity_id == "provider-7"
    assert response.alerts[0].severity == "high"
    assert isinstance(event_bus.published_events[-1], AlertsCreatedEvent)


def test_monitoring_service_returns_no_alerts_below_threshold() -> None:
    service, event_bus = _build_service([_observation(score=0.55)])

    response = service.evaluate(_request())

    assert response.alert_count == 0
    assert response.alerts == []
    assert event_bus.published_events == []


# ---------------------------------------------------------------------------
# E8-S01 — Time-window aggregation
# ---------------------------------------------------------------------------


def test_evaluation_filters_observations_outside_window() -> None:
    now = utc_now()
    inside = _observation(score=0.92, observed_at=now - timedelta(minutes=5))
    outside = _observation(
        entity_id="provider-2",
        score=0.95,
        observed_at=now - timedelta(minutes=120),
    )
    service, _ = _build_service([inside, outside])

    response = service.evaluate(_request(window_minutes=60))

    assert response.alert_count == 1
    assert response.alerts[0].entity_id == "provider-7"


def test_evaluation_requires_min_observations_in_window() -> None:
    now = utc_now()
    service, _ = _build_service(
        [
            _observation(score=0.92, observed_at=now - timedelta(minutes=1)),
        ]
    )

    response = service.evaluate(
        _request(window_minutes=60, min_observations_in_window=2),
    )

    assert response.alert_count == 0


def test_evaluation_min_observations_satisfied_by_repeated_metric() -> None:
    now = utc_now()
    service, _ = _build_service(
        [
            _observation(score=0.91, observed_at=now - timedelta(minutes=10)),
            _observation(score=0.95, observed_at=now - timedelta(minutes=2)),
        ]
    )

    response = service.evaluate(
        _request(window_minutes=60, min_observations_in_window=2),
    )

    assert response.alert_count == 1
    # Highest-scoring observation in the window provides the candidate score.
    assert response.alerts[0].severity == "high"


# ---------------------------------------------------------------------------
# E8-S02 — Deduplication
# ---------------------------------------------------------------------------


def test_dedup_suppresses_repeat_alert_within_window() -> None:
    service, _ = _build_service(
        [_observation(score=0.92)],
        dedup_window_seconds=3600,
    )

    first = service.evaluate(_request())
    second = service.evaluate(_request())

    assert first.alert_count == 1
    assert first.suppressed_count == 0
    assert second.alert_count == 0
    assert second.suppressed_count == 1


def test_dedup_allows_alert_after_window_expires() -> None:
    service, _ = _build_service(
        [_observation(score=0.92)],
        dedup_window_seconds=1,
    )

    first = service.evaluate(_request())
    # Force the dedup index entry to look older than the window.
    index = getattr(service, "_dedup_index")
    index[("provider-7", "claim_volume")] = utc_now() - timedelta(seconds=10)
    second = service.evaluate(_request())

    assert first.alert_count == 1
    assert second.alert_count == 1
    assert second.suppressed_count == 0


def test_dedup_keys_are_per_entity_and_metric() -> None:
    service, _ = _build_service(
        [
            _observation(score=0.92, entity_id="provider-7", metric_name="claim_volume"),
            _observation(score=0.93, entity_id="provider-8", metric_name="claim_volume"),
            _observation(score=0.94, entity_id="provider-7", metric_name="error_rate"),
        ]
    )

    response = service.evaluate(_request())

    assert response.alert_count == 3
    assert response.suppressed_count == 0


# ---------------------------------------------------------------------------
# E8-S03 — Suppression rules
# ---------------------------------------------------------------------------


def test_suppression_rule_excludes_matching_observations() -> None:
    now = utc_now()
    rule = SuppressionRule(
        entity_type="provider",
        metric_name=None,
        start_time=now - timedelta(minutes=1),
        end_time=now + timedelta(minutes=1),
        reason="Maintenance",
    )
    service, _ = _build_service(
        [
            _observation(score=0.92, entity_type="provider"),
            _observation(score=0.93, entity_id="claim-9", entity_type="claim"),
        ],
        suppression_rules=[rule],
    )

    response = service.evaluate(_request())

    assert response.alert_count == 1
    assert response.suppressed_by_rule_count == 1
    assert response.alerts[0].entity_type == "claim"


def test_suppression_rule_outside_time_range_is_ignored() -> None:
    now = utc_now()
    rule = SuppressionRule(
        entity_type="provider",
        metric_name=None,
        start_time=now - timedelta(hours=2),
        end_time=now - timedelta(hours=1),
        reason="Past maintenance",
    )
    service, _ = _build_service(
        [_observation(score=0.92)],
        suppression_rules=[rule],
    )

    response = service.evaluate(_request())

    assert response.alert_count == 1
    assert response.suppressed_by_rule_count == 0


def test_suppression_rule_metric_filter_matches_only_named_metric() -> None:
    now = utc_now()
    rule = SuppressionRule(
        entity_type=None,
        metric_name="claim_volume",
        start_time=now - timedelta(minutes=1),
        end_time=now + timedelta(minutes=1),
        reason="Metric maintenance",
    )
    service, _ = _build_service(
        [
            _observation(score=0.92, metric_name="claim_volume"),
            _observation(score=0.93, entity_id="provider-8", metric_name="error_rate"),
        ],
        suppression_rules=[rule],
    )

    response = service.evaluate(_request())

    assert response.alert_count == 1
    assert response.suppressed_by_rule_count == 1
    assert response.alerts[0].entity_id == "provider-8"


# ---------------------------------------------------------------------------
# E8-S04 — Rate limiting
# ---------------------------------------------------------------------------


def test_rate_limit_caps_alerts_and_prefers_high_severity() -> None:
    observations = [
        _observation(
            entity_id=f"provider-{idx}",
            metric_name=f"metric-{idx}",
            score=0.65 + idx * 0.001,
        )
        for idx in range(3)
    ] + [
        _observation(entity_id="provider-critical", metric_name="claim_volume", score=0.99),
    ]
    service, _ = _build_service(
        observations,
        max_alerts_per_evaluation=2,
    )

    response = service.evaluate(_request())

    assert response.alert_count == 2
    assert response.rate_limited_count == 2
    severities = {alert.severity for alert in response.alerts}
    # The "high" candidate must survive the cap.
    assert "high" in severities


def test_rate_limit_does_not_drop_alerts_when_under_cap() -> None:
    service, _ = _build_service(
        [_observation(score=0.92)],
        max_alerts_per_evaluation=10,
    )

    response = service.evaluate(_request())

    assert response.rate_limited_count == 0
    assert response.alert_count == 1


# ---------------------------------------------------------------------------
# E8-S05 — Lifecycle state machine
# ---------------------------------------------------------------------------


def _build_alert(status: str = "open") -> Alert:
    return Alert(
        id="alert-1",
        entity_id="provider-1",
        entity_type="provider",
        severity="high",
        title="t",
        reasoning="r",
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        status=status,  # pyright: ignore[reportArgumentType]
    )


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("open", "acknowledged"),
        ("open", "dismissed"),
        ("acknowledged", "investigating"),
        ("acknowledged", "open"),
        ("investigating", "resolved"),
        ("investigating", "dismissed"),
        ("investigating", "open"),
        ("resolved", "open"),
        ("dismissed", "open"),
    ],
)
def test_transition_allows_valid_transitions(from_status: str, to_status: str) -> None:
    alert = _build_alert(status=from_status)

    transitioned = transition_alert_status(alert, to_status, actor="ops@example.com")

    assert transitioned.status == to_status
    assert transitioned.updated_at is not None


def test_transition_to_resolved_records_actor_and_notes() -> None:
    alert = _build_alert(status="investigating")

    resolved = transition_alert_status(
        alert, "resolved", actor="ops", resolution_notes="Reviewed."
    )

    assert resolved.resolved_by == "ops"
    assert resolved.resolution_notes == "Reviewed."


def test_transition_to_open_clears_resolution() -> None:
    alert = _build_alert(status="resolved").model_copy(
        update={"resolved_by": "ops", "resolution_notes": "Reviewed."}
    )

    reopened = transition_alert_status(alert, "open", actor="ops")

    assert reopened.status == "open"
    assert reopened.resolved_by is None
    assert reopened.resolution_notes is None


def test_transition_rejects_invalid_transition() -> None:
    alert = _build_alert(status="open")

    with pytest.raises(AlertLifecycleError):
        transition_alert_status(alert, "resolved", actor="ops")


def test_transition_rejects_unknown_status() -> None:
    alert = _build_alert(status="open")

    with pytest.raises(AlertLifecycleError):
        transition_alert_status(alert, "frozen", actor="ops")


def test_transition_to_same_status_is_noop_update() -> None:
    alert = _build_alert(status="open")

    same = transition_alert_status(alert, "open", actor="ops")

    assert same.status == "open"


# ---------------------------------------------------------------------------
# E8-S06 — Alert grouping
# ---------------------------------------------------------------------------


def test_alerts_with_same_entity_type_within_window_are_grouped() -> None:
    service, _ = _build_service(
        [
            _observation(entity_id="provider-1", metric_name="m1", score=0.92),
            _observation(entity_id="provider-2", metric_name="m2", score=0.93),
        ]
    )

    response = service.evaluate(_request())

    assert response.alert_count == 2
    assert len(response.alert_groups) == 1
    group = response.alert_groups[0]
    assert isinstance(group, AlertGroup)
    assert group.entity_type == "provider"
    assert sorted(group.alert_ids) == sorted(alert.id for alert in response.alerts)


def test_alerts_with_distinct_entity_types_are_not_grouped() -> None:
    service, _ = _build_service(
        [
            _observation(entity_id="provider-1", entity_type="provider", score=0.92),
            _observation(entity_id="claim-1", entity_type="claim", score=0.95),
        ]
    )

    response = service.evaluate(_request())

    assert response.alert_count == 2
    assert response.alert_groups == []


def test_single_alert_does_not_form_group() -> None:
    service, _ = _build_service([_observation(score=0.92)])

    response = service.evaluate(_request())

    assert response.alert_count == 1
    assert response.alert_groups == []


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class _ExplodingSource:
    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch:
        raise RuntimeError("boom")


class _ConfigErrorSource:
    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch:
        raise ValueError("missing batch")


def test_evaluate_raises_monitoring_source_error_on_failure() -> None:
    event_bus = InMemoryEventBus()
    service = MonitoringService(_ExplodingSource(), event_bus=event_bus)

    with pytest.raises(MonitoringSourceError):
        service.evaluate(_request())


def test_evaluate_raises_configuration_error_on_value_error() -> None:
    event_bus = InMemoryEventBus()
    service = MonitoringService(_ConfigErrorSource(), event_bus=event_bus)

    with pytest.raises(MonitoringConfigurationError):
        service.evaluate(_request())


def test_severity_below_high_threshold_is_medium() -> None:
    service, _ = _build_service([_observation(score=0.7)])

    response = service.evaluate(_request())

    assert response.alert_count == 1
    assert response.alerts[0].severity == "medium"


def test_suppression_rules_property_returns_copy() -> None:
    rule = SuppressionRule(
        entity_type=None,
        metric_name=None,
        start_time=utc_now(),
        end_time=utc_now() + timedelta(minutes=5),
        reason="test",
    )
    service, _ = _build_service([_observation(score=0.92)], suppression_rules=[rule])

    rules = service.suppression_rules
    rules.clear()

    assert len(service.suppression_rules) == 1
