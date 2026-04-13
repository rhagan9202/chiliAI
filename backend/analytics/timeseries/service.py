"""Service entry point for time-series anomaly detection flows."""

from __future__ import annotations

from math import sqrt

from analytics.timeseries.adapters.protocols import TimeSeriesHistorySourceProtocol
from analytics.timeseries.exceptions import (
    TimeseriesConfigurationError,
    TimeseriesInsufficientHistoryError,
    TimeseriesSourceError,
)
from analytics.timeseries.models import AnomalyPoint, TimeSeriesAnalysisResult, TimeSeriesObservation
from analytics.timeseries.service_models import (
    TimeseriesAnalysisRequest,
    TimeseriesAnalysisResponse,
    TimeseriesAnomaly,
)
from events.protocols import EventBus
from events.types import TimeseriesAnalyzedEvent, TimeseriesAnalyzedReference
from shared.utils import generate_id


class TimeseriesService:
    """Coordinate historical-series loading, anomaly detection, and event publication."""

    # TODO(production): Replace basic z-score anomaly detection with production
    # algorithms: seasonal decomposition (STL), ARIMA/Prophet forecasting,
    # isolation forests, or change-point detection. Add sliding window support
    # for continuous monitoring. Add multi-metric correlation analysis.
    # Current _detect_anomalies() uses a simple z-score threshold over a
    # fixed baseline window — needs configurable detection strategies.

    def __init__(self, history_source: TimeSeriesHistorySourceProtocol, *, event_bus: EventBus) -> None:
        self._history_source = history_source
        self._event_bus = event_bus

    def analyze(self, request: TimeseriesAnalysisRequest) -> TimeseriesAnalysisResponse:
        try:
            series = self._history_source.load_series(
                knowledge_base_id=request.knowledge_base_id,
                entity_id=request.entity_id,
                metric_name=request.metric_name,
            )
        except ValueError as exc:
            raise TimeseriesConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load time-series history.") from exc

        if len(series.observations) < request.min_history:
            raise TimeseriesInsufficientHistoryError(
                "Time series does not contain enough observations for analysis."
            )

        result = TimeSeriesAnalysisResult(
            request_id=generate_id(),
            knowledge_base_id=request.knowledge_base_id,
            entity_id=request.entity_id,
            metric_name=request.metric_name,
            observation_count=len(series.observations),
            anomaly_count=0,
            anomalies=_detect_anomalies(
                series.observations,
                baseline_window=request.baseline_window,
                z_threshold=request.z_threshold,
            ),
        )
        result = result.model_copy(update={"anomaly_count": len(result.anomalies)})

        response = TimeseriesAnalysisResponse(
            request_id=result.request_id,
            knowledge_base_id=result.knowledge_base_id,
            entity_id=result.entity_id,
            metric_name=result.metric_name,
            observation_count=result.observation_count,
            anomaly_count=result.anomaly_count,
            anomalies=[
                TimeseriesAnomaly(
                    observed_at=anomaly.observed_at,
                    observed_value=anomaly.observed_value,
                    expected_value=anomaly.expected_value,
                    deviation=anomaly.deviation,
                    z_score=anomaly.z_score,
                )
                for anomaly in result.anomalies
            ],
        )
        self._event_bus.publish(
            TimeseriesAnalyzedEvent(
                analyses=[
                    TimeseriesAnalyzedReference(
                        knowledge_base_id=response.knowledge_base_id,
                        request_id=response.request_id,
                        entity_id=response.entity_id,
                        metric_name=response.metric_name,
                        observation_count=response.observation_count,
                        anomaly_count=response.anomaly_count,
                    )
                ]
            )
        )
        return response


def create_timeseries_service(
    history_source: TimeSeriesHistorySourceProtocol,
    *,
    event_bus: EventBus,
) -> TimeseriesService:
    """Create the default timeseries service."""

    return TimeseriesService(history_source, event_bus=event_bus)


def _detect_anomalies(
    observations: list[TimeSeriesObservation],
    *,
    baseline_window: int,
    z_threshold: float,
) -> list[AnomalyPoint]:
    anomalies: list[AnomalyPoint] = []
    for index in range(baseline_window, len(observations)):
        baseline = observations[index - baseline_window:index]
        expected_value = _mean(baseline)
        std_dev = _standard_deviation(baseline, expected_value)
        observed_value = observations[index].value
        deviation = abs(observed_value - expected_value)
        z_score = deviation / std_dev if std_dev > 0.0 else (float("inf") if deviation > 0.0 else 0.0)
        if z_score >= z_threshold:
            anomalies.append(
                AnomalyPoint(
                    observed_at=observations[index].observed_at,
                    observed_value=observed_value,
                    expected_value=expected_value,
                    deviation=deviation,
                    z_score=z_score,
                )
            )
    return anomalies


def _mean(observations: list[TimeSeriesObservation]) -> float:
    return sum(observation.value for observation in observations) / len(observations)


def _standard_deviation(observations: list[TimeSeriesObservation], mean_value: float) -> float:
    variance = sum((observation.value - mean_value) ** 2 for observation in observations) / len(observations)
    return sqrt(variance)


__all__ = ["TimeseriesService", "create_timeseries_service"]