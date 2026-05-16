"""Tests for the in-memory entity-metric repository."""

from __future__ import annotations

from analytics.metrics.adapters.in_memory import InMemoryEntityMetricRepository
from analytics.metrics.adapters.protocols import EntityMetricRepository
from analytics.metrics.models import EntityMetricSample


def _sample(metric: str, value: float, *, correlation_id: str = "corr-1") -> EntityMetricSample:
    return EntityMetricSample(
        knowledge_base_id="kb-1",
        entity_id="__graph__",
        metric_name=metric,
        value=value,
        correlation_id=correlation_id,
    )


def test_repository_satisfies_protocol() -> None:
    repo: EntityMetricRepository = InMemoryEntityMetricRepository()
    assert repo.record_metrics([]) == 0


def test_record_metrics_appends_history_and_upserts_current() -> None:
    repo = InMemoryEntityMetricRepository()
    written = repo.record_metrics([_sample("entity_count", 5.0)])
    assert written == 1

    current = repo.load_current_metrics(knowledge_base_id="kb-1", entity_id="__graph__")
    assert len(current) == 1
    assert current[0].value == 5.0


def test_record_metrics_current_reflects_latest_value() -> None:
    repo = InMemoryEntityMetricRepository()
    repo.record_metrics([_sample("entity_count", 5.0)])
    repo.record_metrics([_sample("entity_count", 9.0)])

    current = repo.load_current_metrics(knowledge_base_id="kb-1", entity_id="__graph__")
    assert [c.value for c in current] == [9.0]


def test_load_current_metrics_unknown_entity_returns_empty() -> None:
    repo = InMemoryEntityMetricRepository()
    assert repo.load_current_metrics(knowledge_base_id="kb-x", entity_id="e-x") == []
