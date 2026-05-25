"""Tests for the analytics metrics models."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.metrics.models import (
    GRAPH_SCOPE_ENTITY_ID,
    METRIC_AVG_DEGREE,
    METRIC_ENTITY_COUNT,
    METRIC_RELATIONSHIP_COUNT,
    EntityMetricSample,
    EntityMetricValue,
)


def test_graph_scope_constants() -> None:
    assert GRAPH_SCOPE_ENTITY_ID == "__graph__"
    assert METRIC_ENTITY_COUNT == "entity_count"
    assert METRIC_RELATIONSHIP_COUNT == "relationship_count"
    assert METRIC_AVG_DEGREE == "avg_degree"


def test_entity_metric_sample_defaults_observed_at() -> None:
    sample = EntityMetricSample(
        knowledge_base_id="kb-1",
        entity_id=GRAPH_SCOPE_ENTITY_ID,
        metric_name=METRIC_ENTITY_COUNT,
        value=12.0,
        correlation_id="corr-1",
    )
    assert sample.observed_at.tzinfo is not None


def test_entity_metric_value_round_trips() -> None:
    value = EntityMetricValue(
        knowledge_base_id="kb-1",
        entity_id="claim:c1",
        metric_name=METRIC_AVG_DEGREE,
        value=2.5,
        updated_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    assert value.value == 2.5
