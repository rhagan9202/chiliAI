"""Tests for SAFE-CMS-011 peer-analysis read models."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.peerstats.adapters.in_memory import InMemoryDerivedRiskSignalWriter
from analytics.peerstats.models import DerivedRiskSignal
from analytics.peerstats.peer_analysis import PeerAnalysisService
from config.schema import PeerCohortDefinitionConfig


def _signal(
    entity_id: str,
    *,
    value: float,
    interval_start: datetime,
    metric_name: str = "weekly_billing",
    knowledge_base_id: str = "kb1",
    peer_group_key: str = "provider|cardiology",
    peer_mean: float = 50.0,
    peer_std: float = 20.0,
) -> DerivedRiskSignal:
    return DerivedRiskSignal(
        knowledge_base_id=knowledge_base_id,
        entity_id=entity_id,
        entity_type="provider",
        metric_name=metric_name,
        interval_start=interval_start,
        peer_group_key=peer_group_key,
        aggregate_value=value,
        peer_mean=peer_mean,
        peer_std=peer_std,
        z_score=0.0 if peer_std == 0 else (value - peer_mean) / peer_std,
        signal_value=min(max(value / 100.0, 0.0), 1.0),
        weight=1.0,
        rationale="weekly billing compared to specialty peers",
        correlation_id="corr-1",
    )


def test_peer_analysis_returns_latest_metric_context_with_percentile() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    older = datetime(2026, 1, 5, tzinfo=timezone.utc)
    latest = datetime(2026, 1, 12, tzinfo=timezone.utc)
    writer.write_signals(
        [
            _signal("provider:target", value=80.0, interval_start=older),
            _signal("provider:a", value=10.0, interval_start=latest),
            _signal("provider:b", value=50.0, interval_start=latest),
            _signal("provider:c", value=75.0, interval_start=latest),
            _signal("provider:target", value=100.0, interval_start=latest),
        ]
    )

    response = PeerAnalysisService(writer, min_cohort_size=4).compare_entity(
        knowledge_base_id="kb1",
        entity_id="provider:target",
    )

    assert response.knowledge_base_id == "kb1"
    assert response.entity_id == "provider:target"
    assert len(response.metrics) == 1
    metric = response.metrics[0]
    assert metric.metric_name == "weekly_billing"
    assert metric.interval_start == latest
    assert metric.entity_value == 100.0
    assert metric.peer_mean == 50.0
    assert metric.peer_std == 20.0
    assert metric.z_score == 2.5
    assert metric.cohort_size == 4
    assert metric.percentile == 100.0
    assert metric.confidence == "normal"


def test_peer_analysis_is_kb_scoped_and_can_filter_metric() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    interval = datetime(2026, 1, 12, tzinfo=timezone.utc)
    writer.write_signals(
        [
            _signal("provider:target", value=90.0, interval_start=interval),
            _signal("provider:peer", value=10.0, interval_start=interval),
            _signal(
                "provider:target",
                value=5.0,
                interval_start=interval,
                metric_name="daily_claim_count",
            ),
            _signal(
                "provider:target",
                value=999.0,
                interval_start=interval,
                knowledge_base_id="kb2",
            ),
        ]
    )

    response = PeerAnalysisService(writer, min_cohort_size=2).compare_entity(
        knowledge_base_id="kb1",
        entity_id="provider:target",
        metric_name="weekly_billing",
    )

    assert [metric.metric_name for metric in response.metrics] == ["weekly_billing"]
    assert response.metrics[0].entity_value == 90.0
    assert response.metrics[0].cohort_size == 2


def test_peer_analysis_marks_small_or_degenerate_cohort_low_confidence() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    interval = datetime(2026, 1, 12, tzinfo=timezone.utc)
    writer.write_signals(
        [
            _signal(
                "provider:target",
                value=20.0,
                interval_start=interval,
                peer_mean=20.0,
                peer_std=0.0,
            ),
            _signal("provider:peer", value=20.0, interval_start=interval),
        ]
    )

    response = PeerAnalysisService(writer, min_cohort_size=5).compare_entity(
        knowledge_base_id="kb1",
        entity_id="provider:target",
    )

    assert response.metrics[0].cohort_size == 2
    assert response.metrics[0].confidence == "low"
    assert response.metrics[0].confidence_reason == "small_or_degenerate_cohort"


def test_peer_analysis_includes_cohort_membership_and_distribution() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    interval = datetime(2026, 1, 12, tzinfo=timezone.utc)
    writer.write_signals(
        [
            _signal("provider:target", value=100.0, interval_start=interval),
            _signal("provider:a", value=10.0, interval_start=interval),
            _signal("provider:b", value=50.0, interval_start=interval),
            _signal("provider:c", value=75.0, interval_start=interval),
        ]
    )

    response = PeerAnalysisService(
        writer,
        min_cohort_size=4,
        cohort_definitions=[
            PeerCohortDefinitionConfig(
                id="provider_specialty_billing",
                label="Provider specialty billing",
                entity_type="provider",
                peer_metric="weekly_billing",
                group_by=["specialty"],
                version="v1",
            )
        ],
    ).compare_entity(
        knowledge_base_id="kb1",
        entity_id="provider:target",
    )

    metric = response.metrics[0]
    assert metric.distribution is not None
    assert metric.distribution.count == 4
    assert metric.distribution.p50 == 62.5
    assert metric.distribution.p90 == 92.5
    assert metric.cohort is not None
    assert metric.cohort.id == "provider_specialty_billing"
    assert metric.cohort.version == "v1"
    assert metric.cohort.group_values == {"specialty": "cardiology"}
    assert metric.cohort.member_entity_ids == [
        "provider:a",
        "provider:b",
        "provider:c",
        "provider:target",
    ]
    assert metric.cohort.exclusions == []
