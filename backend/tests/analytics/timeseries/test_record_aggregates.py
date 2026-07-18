"""Record-aggregate series source over the peerstats column protocol."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from analytics.peerstats.models import PeerAggregate
from analytics.timeseries.adapters.record_aggregates import (
    RecordAggregateTimeSeriesSource,
    load_entity_series_map,
)
from config.schema import PeerMetricSpec, TimeseriesMetricSpec


class _FakeColumnSource:
    """Protocol double returning canned aggregates; records the spec used."""

    def __init__(self, aggregates: list[PeerAggregate]) -> None:
        self._aggregates = aggregates
        self.last_spec: PeerMetricSpec | None = None

    def load_interval_aggregates(
        self,
        *,
        knowledge_base_id: str,
        spec: PeerMetricSpec,
        interval_starts: list[datetime],
    ) -> list[PeerAggregate]:
        self.last_spec = spec
        return self._aggregates


def _spec() -> TimeseriesMetricSpec:
    return TimeseriesMetricSpec(
        name="weekly_billing_self",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="npi",
        value_column="amount",
        aggregation="sum",
        interval="week",
        time_column="service_date",
    )


def _aggregate(entity_id: str, day: int, value: float) -> PeerAggregate:
    return PeerAggregate(
        entity_id=entity_id,
        entity_type="provider",
        peer_group_key="provider",
        interval_start=datetime(2026, 1, day, tzinfo=UTC),
        aggregate_value=value,
    )


def test_series_map_groups_and_orders_per_entity() -> None:
    source = _FakeColumnSource(
        [
            _aggregate("provider:1", 8, 200.0),
            _aggregate("provider:1", 1, 100.0),
            _aggregate("provider:2", 1, 50.0),
        ]
    )
    series_map = load_entity_series_map(source, knowledge_base_id="kb-1", spec=_spec())
    assert set(series_map) == {"provider:1", "provider:2"}
    values = [obs.value for obs in series_map["provider:1"].observations]
    assert values == [100.0, 200.0]
    assert series_map["provider:1"].metric_name == "weekly_billing_self"
    assert source.last_spec is not None
    assert source.last_spec.value_column == "amount"
    assert source.last_spec.time_column == "service_date"


def test_load_series_returns_one_entity_and_raises_when_absent() -> None:
    source = RecordAggregateTimeSeriesSource(
        _FakeColumnSource([_aggregate("provider:1", 1, 100.0)]), specs=[_spec()]
    )
    series = source.load_series(
        knowledge_base_id="kb-1", entity_id="provider:1", metric_name="weekly_billing_self"
    )
    assert series.observations[0].value == 100.0
    with pytest.raises(ValueError):
        source.load_series(
            knowledge_base_id="kb-1", entity_id="provider:9", metric_name="weekly_billing_self"
        )
    with pytest.raises(ValueError):
        source.load_series(
            knowledge_base_id="kb-1", entity_id="provider:1", metric_name="unknown"
        )


def test_metric_names_preserve_config_order_and_range_is_empty() -> None:
    source = RecordAggregateTimeSeriesSource(_FakeColumnSource([]), specs=[_spec()])
    assert source.metric_names() == ["weekly_billing_self"]
    assert (
        source.load_metric_range(
            knowledge_base_id="kb-1",
            metric_name="weekly_billing_self",
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 2, 1, tzinfo=UTC),
        )
        == []
    )
