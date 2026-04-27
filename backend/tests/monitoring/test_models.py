"""Tests for monitoring module models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from monitoring.models import (
    AlertCandidate,
    AlertGroup,
    MonitoringBatch,
    MonitoringObservation,
    SuppressionRule,
)
from monitoring.service_models import MonitoringEvaluationRequest


def test_monitoring_batch_requires_observations() -> None:
    with pytest.raises(ValueError, match="at least one observation"):
        MonitoringBatch(knowledge_base_id="kb-1", batch_id="batch-1", observations=[])


def test_monitoring_request_requires_ordered_thresholds() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        MonitoringEvaluationRequest(
            knowledge_base_id="kb-1",
            batch_id="batch-1",
            medium_threshold=0.8,
            high_threshold=0.7,
        )


def test_alert_candidate_round_trip() -> None:
    candidate = AlertCandidate(
        entity_id="provider-1",
        entity_type="provider",
        severity="high",
        title="t",
        reasoning="r",
        score=0.9,
        metric_name="claim_volume",
    )
    assert candidate.metric_name == "claim_volume"


def test_suppression_rule_requires_end_after_start() -> None:
    start = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="end_time"):
        SuppressionRule(
            entity_type=None,
            metric_name=None,
            start_time=start,
            end_time=start,
            reason="invalid",
        )


def test_suppression_rule_matches_with_wildcards() -> None:
    now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    rule = SuppressionRule(
        entity_type=None,
        metric_name=None,
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
        reason="full wildcard",
    )

    assert rule.matches(entity_type="provider", metric_name="m1", now=now)


def test_suppression_rule_filters_by_entity_type() -> None:
    now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    rule = SuppressionRule(
        entity_type="provider",
        metric_name=None,
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
        reason="provider only",
    )

    assert rule.matches(entity_type="provider", metric_name="m", now=now) is True
    assert rule.matches(entity_type="claim", metric_name="m", now=now) is False


def test_suppression_rule_filters_by_metric() -> None:
    now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    rule = SuppressionRule(
        entity_type=None,
        metric_name="claim_volume",
        start_time=now - timedelta(hours=1),
        end_time=now + timedelta(hours=1),
        reason="metric only",
    )

    assert rule.matches(entity_type="provider", metric_name="claim_volume", now=now)
    assert (
        rule.matches(entity_type="provider", metric_name="error_rate", now=now)
        is False
    )


def test_suppression_rule_outside_time_range() -> None:
    now = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
    rule = SuppressionRule(
        entity_type=None,
        metric_name=None,
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=2),
        reason="future",
    )

    assert rule.matches(entity_type="provider", metric_name="m", now=now) is False


def test_alert_group_round_trip() -> None:
    group = AlertGroup(
        group_id="grp-1",
        alert_ids=["a-1", "a-2"],
        entity_type="provider",
        created_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        correlation_reason="Same entity_type 'provider' within 300s window",
    )
    assert group.alert_ids == ["a-1", "a-2"]
    assert group.correlation_reason.startswith("Same")


def test_monitoring_observation_default_observed_at_is_aware() -> None:
    obs = MonitoringObservation(
        entity_id="e",
        entity_type="provider",
        metric_name="m",
        score=0.5,
        rationale="r",
    )
    assert obs.observed_at.tzinfo is not None
