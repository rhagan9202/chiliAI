"""Tests for the timeseries service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.exceptions import TimeseriesInsufficientHistoryError
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from analytics.timeseries.service import create_timeseries_service
from analytics.timeseries.service_models import TimeseriesAnalysisRequest
from events.adapters.in_memory import InMemoryEventBus
from events.types import TimeseriesAnalyzedEvent


def test_timeseries_service_detects_spike_and_publishes_event() -> None:
    event_bus = InMemoryEventBus()
    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series([10.0, 11.0, 10.0, 11.0, 10.0, 45.0])]),
        event_bus=event_bus,
    )

    response = service.analyze(
        TimeseriesAnalysisRequest(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            metric_name="claim_volume",
            baseline_window=3,
            min_history=5,
            z_threshold=2.0,
        )
    )

    assert response.anomaly_count == 1
    assert response.anomalies[0].observed_value == 45.0
    assert isinstance(event_bus.published_events[-1], TimeseriesAnalyzedEvent)


def test_timeseries_service_raises_for_insufficient_history() -> None:
    event_bus = InMemoryEventBus()
    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series([10.0, 11.0, 12.0])]),
        event_bus=event_bus,
    )

    with pytest.raises(TimeseriesInsufficientHistoryError, match="enough observations"):
        service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id="kb-1",
                entity_id="provider-7",
                metric_name="claim_volume",
                baseline_window=2,
                min_history=4,
            )
        )


def _build_series(values: list[float]) -> TimeSeriesSeries:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return TimeSeriesSeries(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        metric_name="claim_volume",
        observations=[
            TimeSeriesObservation(observed_at=start + timedelta(days=index), value=value)
            for index, value in enumerate(values)
        ],
    )