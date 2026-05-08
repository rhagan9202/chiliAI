"""Tests for the in-memory timeseries adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries


def test_in_memory_history_source_returns_seeded_series() -> None:
    series = TimeSeriesSeries(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        metric_name="claim_volume",
        observations=[
            TimeSeriesObservation(observed_at=datetime(2024, 1, 1, tzinfo=timezone.utc), value=10.0)
        ],
    )
    source = InMemoryTimeSeriesHistorySource(series=[series])

    loaded = source.load_series(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        metric_name="claim_volume",
    )

    assert loaded == series


def test_in_memory_history_source_raises_for_unknown_series() -> None:
    source = InMemoryTimeSeriesHistorySource()

    with pytest.raises(ValueError, match="No time series registered"):
        source.load_series(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            metric_name="missing",
        )


def test_in_memory_history_source_load_metric_range_filters_window() -> None:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    source = InMemoryTimeSeriesHistorySource(
        metric_observations={
            ("kb-1", "claim_volume"): [
                TimeSeriesObservation(observed_at=base + timedelta(days=index), value=float(index))
                for index in range(4)
            ],
        }
    )

    points = source.load_metric_range(
        knowledge_base_id="kb-1",
        metric_name="claim_volume",
        start=base + timedelta(days=1),
        end=base + timedelta(days=2),
    )

    assert [point.value for point in points] == [1.0, 2.0]


def test_in_memory_history_source_load_metric_range_returns_empty_when_unseeded() -> None:
    source = InMemoryTimeSeriesHistorySource()
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)

    points = source.load_metric_range(
        knowledge_base_id="kb-missing",
        metric_name="claim_volume",
        start=base,
        end=base + timedelta(days=1),
    )

    assert points == []