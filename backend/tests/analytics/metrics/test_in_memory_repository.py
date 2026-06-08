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


def _sample_for_kb(kb: str, metric: str, value: float) -> EntityMetricSample:
    return EntityMetricSample(
        knowledge_base_id=kb,
        entity_id="__graph__",
        metric_name=metric,
        value=value,
        correlation_id="corr-del",
    )


def test_delete_by_kb_purges_history_and_current_for_target_kb() -> None:
    repo = InMemoryEntityMetricRepository()
    repo.record_metrics([_sample_for_kb("kb-a", "entity_count", 1.0)])
    repo.record_metrics([_sample_for_kb("kb-b", "entity_count", 2.0)])

    removed = repo.delete_by_kb("kb-a")

    # 1 history row removed for kb-a.
    assert removed == 1
    # A subsequent delete returns 0 — history is gone (idempotency also serves as
    # the "history is empty for this KB" assertion without touching private state).
    assert repo.delete_by_kb("kb-a") == 0
    # Current for kb-a is gone.
    current_a = repo.load_current_metrics(knowledge_base_id="kb-a", entity_id="__graph__")
    assert current_a == []
    # kb-b is intact in both history (delete_by_kb returns 1) and current.
    assert repo.delete_by_kb("kb-b") == 1
    current_b_after = repo.load_current_metrics(knowledge_base_id="kb-b", entity_id="__graph__")
    assert current_b_after == []


def test_delete_by_kb_idempotent() -> None:
    repo = InMemoryEntityMetricRepository()
    repo.record_metrics([_sample_for_kb("kb-a", "entity_count", 5.0)])

    first = repo.delete_by_kb("kb-a")
    assert first == 1
    second = repo.delete_by_kb("kb-a")
    assert second == 0


def test_delete_by_kb_unknown_kb_returns_zero() -> None:
    repo = InMemoryEntityMetricRepository()
    assert repo.delete_by_kb("kb-nonexistent") == 0
