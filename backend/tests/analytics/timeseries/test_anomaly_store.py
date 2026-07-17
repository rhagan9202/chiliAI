"""In-memory timeseries anomaly store behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from analytics.timeseries.adapters.in_memory import InMemoryTimeseriesAnomalyStore
from analytics.timeseries.models import TimeseriesAnomalyRecord


def _record(observed_at: datetime, *, severity: float = 0.8) -> TimeseriesAnomalyRecord:
    return TimeseriesAnomalyRecord(
        knowledge_base_id="kb-1",
        entity_id="provider:1",
        metric_name="weekly_billing_self",
        observed_at=observed_at,
        observed_value=900.0,
        expected_value=100.0,
        z_score=3.2,
        severity=severity,
        detection_strategy="z_score",
        correlation_id="corr-1",
    )


def test_write_then_load_returns_ordered_anomalies() -> None:
    store = InMemoryTimeseriesAnomalyStore()
    later = _record(datetime(2026, 2, 1, tzinfo=UTC))
    earlier = _record(datetime(2026, 1, 1, tzinfo=UTC))
    assert store.write_anomalies([later, earlier]) == 2
    loaded = store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name="weekly_billing_self"
    )
    assert [r.observed_at for r in loaded] == [earlier.observed_at, later.observed_at]


def test_write_upserts_on_conflict_key() -> None:
    store = InMemoryTimeseriesAnomalyStore()
    when = datetime(2026, 1, 1, tzinfo=UTC)
    store.write_anomalies([_record(when, severity=0.5)])
    store.write_anomalies([_record(when, severity=0.9)])
    loaded = store.load_anomalies(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name="weekly_billing_self"
    )
    assert len(loaded) == 1
    assert loaded[0].severity == 0.9


def test_delete_by_kb_scopes_to_one_kb() -> None:
    store = InMemoryTimeseriesAnomalyStore()
    store.write_anomalies([_record(datetime(2026, 1, 1, tzinfo=UTC))])
    other = _record(datetime(2026, 1, 1, tzinfo=UTC)).model_copy(
        update={"knowledge_base_id": "kb-2"}
    )
    store.write_anomalies([other])
    assert store.delete_by_kb("kb-1") == 1
    assert store.load_anomalies(
        knowledge_base_id="kb-2", entity_id="provider:1", metric_name="weekly_billing_self"
    )
