"""Tests for the in-memory timeseries adapter."""

from __future__ import annotations

from datetime import datetime, timezone

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