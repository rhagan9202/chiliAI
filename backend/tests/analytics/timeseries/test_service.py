"""Tests for the timeseries service."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from analytics.timeseries.adapters.in_memory import InMemoryTimeSeriesHistorySource
from analytics.timeseries.adapters.protocols import TimeSeriesHistorySourceProtocol
from analytics.timeseries.exceptions import (
    TimeseriesConfigurationError,
    TimeseriesInsufficientHistoryError,
    TimeseriesSourceError,
)
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from analytics.timeseries.service import create_timeseries_service
from analytics.timeseries.service_models import (
    TimeseriesAnalysisRequest,
    TimeseriesQueryRequest,
)
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


def test_timeseries_service_query_metric_filters_range() -> None:
    source = InMemoryTimeSeriesHistorySource()
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    source.put_metric_observations(
        knowledge_base_id="kb-1",
        metric_name="claim_volume",
        observations=[
            TimeSeriesObservation(observed_at=base + timedelta(days=index), value=float(index))
            for index in range(5)
        ],
    )
    service = create_timeseries_service(source, event_bus=InMemoryEventBus())

    response = service.query_metric(
        TimeseriesQueryRequest(
            knowledge_base_id="kb-1",
            metric_name="claim_volume",
            start=base + timedelta(days=1),
            end=base + timedelta(days=3),
        )
    )

    assert [point.value for point in response.points] == [1.0, 2.0, 3.0]


class _ValueErrorHistorySource:
    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        raise NotImplementedError

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        del knowledge_base_id, metric_name, start, end
        raise ValueError("invalid range")


class _RuntimeErrorHistorySource:
    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        raise NotImplementedError

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        del knowledge_base_id, metric_name, start, end
        raise RuntimeError("source down")


class _AnalyzeValueErrorSource:
    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        del knowledge_base_id, entity_id, metric_name
        raise ValueError("missing series")

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        del knowledge_base_id, metric_name, start, end
        raise NotImplementedError


class _AnalyzeRuntimeErrorSource:
    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        del knowledge_base_id, entity_id, metric_name
        raise RuntimeError("source down")

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        del knowledge_base_id, metric_name, start, end
        raise NotImplementedError


def test_timeseries_service_query_metric_translates_value_error() -> None:
    source: TimeSeriesHistorySourceProtocol = _ValueErrorHistorySource()
    service = create_timeseries_service(source, event_bus=InMemoryEventBus())
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(TimeseriesConfigurationError, match="invalid range"):
        service.query_metric(
            TimeseriesQueryRequest(
                knowledge_base_id="kb-1",
                metric_name="claim_volume",
                start=base,
                end=base + timedelta(days=1),
            )
        )


def test_timeseries_service_query_metric_translates_runtime_error() -> None:
    source: TimeSeriesHistorySourceProtocol = _RuntimeErrorHistorySource()
    service = create_timeseries_service(source, event_bus=InMemoryEventBus())
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(TimeseriesSourceError, match="metric range"):
        service.query_metric(
            TimeseriesQueryRequest(
                knowledge_base_id="kb-1",
                metric_name="claim_volume",
                start=base,
                end=base + timedelta(days=1),
            )
        )


def test_timeseries_service_analyze_translates_value_error() -> None:
    source: TimeSeriesHistorySourceProtocol = _AnalyzeValueErrorSource()
    service = create_timeseries_service(source, event_bus=InMemoryEventBus())

    with pytest.raises(TimeseriesConfigurationError, match="missing series"):
        service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id="kb-1",
                entity_id="provider-7",
                metric_name="claim_volume",
                baseline_window=3,
                min_history=5,
            )
        )


def test_timeseries_service_analyze_translates_runtime_error() -> None:
    source: TimeSeriesHistorySourceProtocol = _AnalyzeRuntimeErrorSource()
    service = create_timeseries_service(source, event_bus=InMemoryEventBus())

    with pytest.raises(TimeseriesSourceError, match="time-series history"):
        service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id="kb-1",
                entity_id="provider-7",
                metric_name="claim_volume",
                baseline_window=3,
                min_history=5,
            )
        )


# --- E7-S03: window_size ----------------------------------------------------


def test_timeseries_service_window_size_truncates_series() -> None:
    values = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0, 45.0]
    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series(values)]),
        event_bus=InMemoryEventBus(),
    )

    response = service.analyze(
        TimeseriesAnalysisRequest(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            metric_name="claim_volume",
            baseline_window=3,
            min_history=5,
            z_threshold=2.0,
            window_size=5,
        )
    )

    assert response.observation_count == 5
    assert response.anomaly_count == 1
    assert response.anomalies[0].observed_value == 45.0


def test_timeseries_service_window_size_changes_results() -> None:
    values = [10.0] * 20 + [12.0, 14.0, 16.0, 50.0]
    series = _build_series(values)
    full_service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[series]),
        event_bus=InMemoryEventBus(),
    )
    windowed_service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[series]),
        event_bus=InMemoryEventBus(),
    )
    base_request = TimeseriesAnalysisRequest(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        metric_name="claim_volume",
        baseline_window=3,
        min_history=5,
        z_threshold=2.0,
    )

    full = full_service.analyze(base_request)
    windowed = windowed_service.analyze(
        base_request.model_copy(update={"window_size": 6})
    )

    assert full.observation_count == len(values)
    assert windowed.observation_count == 6
    assert full.anomaly_count != windowed.anomaly_count or [
        anomaly.observed_value for anomaly in full.anomalies
    ] != [anomaly.observed_value for anomaly in windowed.anomalies]


def test_timeseries_service_window_size_zero_raises_configuration_error() -> None:
    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series([10.0] * 8)]),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(TimeseriesConfigurationError, match="window_size"):
        service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id="kb-1",
                entity_id="provider-7",
                metric_name="claim_volume",
                baseline_window=3,
                min_history=5,
                window_size=0,
            )
        )


def test_timeseries_service_window_size_negative_raises_configuration_error() -> None:
    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series([10.0] * 8)]),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(TimeseriesConfigurationError, match="window_size"):
        service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id="kb-1",
                entity_id="provider-7",
                metric_name="claim_volume",
                baseline_window=3,
                min_history=5,
                window_size=-2,
            )
        )


# --- E7-S01: STL strategy ---------------------------------------------------


def test_timeseries_service_stl_strategy_flags_outlier() -> None:
    pytest.importorskip("statsmodels")
    seasonal_pattern = [10.0, 14.0, 18.0, 14.0, 10.0, 6.0, 2.0]
    values = seasonal_pattern * 3
    values[10] = 60.0
    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series(values)]),
        event_bus=InMemoryEventBus(),
    )

    response = service.analyze(
        TimeseriesAnalysisRequest(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            metric_name="claim_volume",
            baseline_window=3,
            min_history=5,
            z_threshold=2.0,
            detection_strategy="stl_decomposition",
        )
    )

    flagged_values = {anomaly.observed_value for anomaly in response.anomalies}
    assert 60.0 in flagged_values


def test_timeseries_service_stl_reduces_false_positives_vs_zscore() -> None:
    pytest.importorskip("statsmodels")
    seasonal_pattern = [10.0, 14.0, 18.0, 14.0, 10.0, 6.0, 2.0]
    values = seasonal_pattern * 3

    zscore_service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series(values)]),
        event_bus=InMemoryEventBus(),
    )
    stl_service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series(values)]),
        event_bus=InMemoryEventBus(),
    )

    request = TimeseriesAnalysisRequest(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        metric_name="claim_volume",
        baseline_window=3,
        min_history=5,
        z_threshold=2.0,
    )
    zscore_response = zscore_service.analyze(request)
    stl_response = stl_service.analyze(
        request.model_copy(update={"detection_strategy": "stl_decomposition"})
    )

    assert zscore_response.anomaly_count > 0
    assert stl_response.anomaly_count <= zscore_response.anomaly_count


def test_timeseries_service_stl_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name.startswith("statsmodels"):
            raise ImportError("statsmodels not available")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series([10.0] * 14)]),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(TimeseriesConfigurationError, match="analytics extra"):
        service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id="kb-1",
                entity_id="provider-7",
                metric_name="claim_volume",
                baseline_window=3,
                min_history=5,
                detection_strategy="stl_decomposition",
            )
        )


# --- E7-S02: Isolation forest strategy --------------------------------------


def test_timeseries_service_isolation_forest_flags_planted_outliers() -> None:
    pytest.importorskip("sklearn")
    base_values = [10.0 + 0.1 * math.sin(index) for index in range(40)]
    base_values[12] = 95.0
    base_values[27] = -45.0

    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series(base_values)]),
        event_bus=InMemoryEventBus(),
    )

    response = service.analyze(
        TimeseriesAnalysisRequest(
            knowledge_base_id="kb-1",
            entity_id="provider-7",
            metric_name="claim_volume",
            baseline_window=3,
            min_history=5,
            detection_strategy="isolation_forest",
            contamination=0.1,
        )
    )

    flagged = {anomaly.observed_value for anomaly in response.anomalies}
    assert 95.0 in flagged
    assert -45.0 in flagged


def test_timeseries_service_isolation_forest_respects_contamination() -> None:
    pytest.importorskip("sklearn")
    values = [10.0 + 0.05 * index for index in range(40)]
    values[5] = 80.0
    values[20] = 80.0
    values[35] = 80.0

    low_service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series(values)]),
        event_bus=InMemoryEventBus(),
    )
    high_service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series(values)]),
        event_bus=InMemoryEventBus(),
    )

    base = TimeseriesAnalysisRequest(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        metric_name="claim_volume",
        baseline_window=3,
        min_history=5,
        detection_strategy="isolation_forest",
        contamination=0.05,
    )
    low = low_service.analyze(base)
    high = high_service.analyze(base.model_copy(update={"contamination": 0.3}))

    assert high.anomaly_count >= low.anomaly_count


def test_timeseries_service_isolation_forest_missing_dependency_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name.startswith("sklearn"):
            raise ImportError("sklearn not available")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    service = create_timeseries_service(
        InMemoryTimeSeriesHistorySource(series=[_build_series([10.0] * 14)]),
        event_bus=InMemoryEventBus(),
    )

    with pytest.raises(TimeseriesConfigurationError, match="analytics extra"):
        service.analyze(
            TimeseriesAnalysisRequest(
                knowledge_base_id="kb-1",
                entity_id="provider-7",
                metric_name="claim_volume",
                baseline_window=3,
                min_history=5,
                detection_strategy="isolation_forest",
            )
        )
