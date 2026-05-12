"""Service entry point for time-series anomaly detection flows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from math import sqrt
from typing import Protocol, SupportsFloat, SupportsInt, cast

from analytics.timeseries.adapters.protocols import TimeSeriesHistorySourceProtocol
from analytics.timeseries.exceptions import (
    TimeseriesConfigurationError,
    TimeseriesInsufficientHistoryError,
    TimeseriesSourceError,
)
from analytics.timeseries.models import AnomalyPoint, TimeSeriesAnalysisResult, TimeSeriesObservation
from analytics.timeseries.service_models import (
    DetectionStrategy,
    MetricTimeseriesResponse,
    TimeseriesAnalysisRequest,
    TimeseriesAnalysisResponse,
    TimeseriesAnomaly,
    TimeseriesPoint,
    TimeseriesQueryRequest,
)
from events.protocols import EventBus
from events.types import TimeseriesAnalyzedEvent, TimeseriesAnalyzedReference
from shared.utils import generate_id


class _DecompositionResult(Protocol):
    """Typed subset returned by statsmodels seasonal decomposition."""

    resid: Sequence[object]
    trend: Sequence[object]
    seasonal: Sequence[object]


class _IsolationForestEstimator(Protocol):
    """Typed subset of sklearn's IsolationForest used by this service."""

    def fit(self, X: list[list[float]]) -> object:
        """Fit the estimator to the feature matrix."""

        ...

    def predict(self, X: list[list[float]]) -> Sequence[object]:
        """Return labels where -1 denotes an anomaly."""

        ...

    def score_samples(self, X: list[list[float]]) -> Sequence[object]:
        """Return anomaly score samples for the feature matrix."""

        ...


class TimeseriesService:
    """Coordinate historical-series loading, anomaly detection, and event publication."""

    def __init__(self, history_source: TimeSeriesHistorySourceProtocol, *, event_bus: EventBus) -> None:
        self._history_source = history_source
        self._event_bus = event_bus

    def analyze(self, request: TimeseriesAnalysisRequest) -> TimeseriesAnalysisResponse:
        if request.window_size is not None and request.window_size <= 0:
            raise TimeseriesConfigurationError(
                "TimeseriesAnalysisRequest window_size must be a positive integer."
            )

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

        observations = list(series.observations)
        if request.window_size is not None and len(observations) > request.window_size:
            observations = observations[-request.window_size :]

        if len(observations) < request.min_history:
            raise TimeseriesInsufficientHistoryError(
                "Time series does not contain enough observations for analysis."
            )

        anomalies = self._dispatch_detection(
            strategy=request.detection_strategy,
            observations=observations,
            baseline_window=request.baseline_window,
            z_threshold=request.z_threshold,
            contamination=request.contamination,
        )

        result = TimeSeriesAnalysisResult(
            request_id=generate_id(),
            knowledge_base_id=request.knowledge_base_id,
            entity_id=request.entity_id,
            metric_name=request.metric_name,
            observation_count=len(observations),
            anomaly_count=len(anomalies),
            anomalies=anomalies,
        )

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


    def query_metric(self, request: TimeseriesQueryRequest) -> MetricTimeseriesResponse:
        try:
            observations = self._history_source.load_metric_range(
                knowledge_base_id=request.knowledge_base_id,
                metric_name=request.metric_name,
                start=request.start,
                end=request.end,
            )
        except ValueError as exc:
            raise TimeseriesConfigurationError(str(exc)) from exc
        except Exception as exc:
            raise TimeseriesSourceError("Failed to load metric range.") from exc

        points = [
            TimeseriesPoint(observed_at=observation.observed_at, value=observation.value)
            for observation in observations
        ]
        return MetricTimeseriesResponse(
            knowledge_base_id=request.knowledge_base_id,
            metric_name=request.metric_name,
            start=request.start,
            end=request.end,
            points=points,
        )

    def _dispatch_detection(
        self,
        *,
        strategy: DetectionStrategy,
        observations: list[TimeSeriesObservation],
        baseline_window: int,
        z_threshold: float,
        contamination: float,
    ) -> list[AnomalyPoint]:
        if strategy == "z_score":
            return _detect_anomalies(
                observations,
                baseline_window=baseline_window,
                z_threshold=z_threshold,
            )
        if strategy == "stl_decomposition":
            return _detect_anomalies_stl(
                observations,
                z_threshold=z_threshold,
            )
        if strategy == "isolation_forest":
            return _detect_anomalies_isolation_forest(
                observations,
                contamination=contamination,
            )
        raise TimeseriesConfigurationError(
            f"Unknown detection strategy: {strategy!r}."
        )


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


def _detect_anomalies_stl(
    observations: list[TimeSeriesObservation],
    *,
    z_threshold: float,
) -> list[AnomalyPoint]:
    try:
        statsmodels_seasonal = __import__(
            "statsmodels.tsa.seasonal",
            fromlist=["seasonal_decompose"],
        )
    except ImportError as exc:
        raise TimeseriesConfigurationError(
            "STL strategy requires the analytics extra (statsmodels)."
        ) from exc

    if len(observations) < 4:
        raise TimeseriesInsufficientHistoryError(
            "STL decomposition requires at least four observations."
        )

    values = [observation.value for observation in observations]
    period = _infer_period(len(values))
    seasonal_decompose = cast(
        Callable[..., _DecompositionResult],
        getattr(statsmodels_seasonal, "seasonal_decompose"),
    )
    try:
        decomposition = seasonal_decompose(
            values,
            model="additive",
            period=period,
            extrapolate_trend="freq",
        )
    except ValueError as exc:
        raise TimeseriesConfigurationError(
            f"STL decomposition failed: {exc}"
        ) from exc

    residuals = [_coerce_float(value) for value in decomposition.resid]
    trend = [_coerce_float(value) for value in decomposition.trend]
    seasonal = [_coerce_float(value) for value in decomposition.seasonal]

    finite_residuals = [value for value in residuals if _is_finite(value)]
    if not finite_residuals:
        return []

    residual_mean = sum(finite_residuals) / len(finite_residuals)
    residual_variance = sum(
        (value - residual_mean) ** 2 for value in finite_residuals
    ) / len(finite_residuals)
    residual_std = sqrt(residual_variance)

    anomalies: list[AnomalyPoint] = []
    for index, observation in enumerate(observations):
        residual = residuals[index]
        if not _is_finite(residual):
            continue
        deviation = abs(residual - residual_mean)
        if residual_std > 0.0:
            z_score = deviation / residual_std
        elif deviation > 0.0:
            z_score = float("inf")
        else:
            z_score = 0.0
        if z_score >= z_threshold:
            expected_value = (
                trend[index] + seasonal[index]
                if _is_finite(trend[index]) and _is_finite(seasonal[index])
                else observation.value - residual
            )
            anomalies.append(
                AnomalyPoint(
                    observed_at=observation.observed_at,
                    observed_value=observation.value,
                    expected_value=expected_value,
                    deviation=abs(observation.value - expected_value),
                    z_score=z_score,
                )
            )
    return anomalies


def _detect_anomalies_isolation_forest(
    observations: list[TimeSeriesObservation],
    *,
    contamination: float,
) -> list[AnomalyPoint]:
    try:
        sklearn_ensemble = __import__(
            "sklearn.ensemble",
            fromlist=["IsolationForest"],
        )
    except ImportError as exc:
        raise TimeseriesConfigurationError(
            "Isolation forest strategy requires the analytics extra (scikit-learn)."
        ) from exc

    values = [observation.value for observation in observations]
    feature_matrix: list[list[float]] = [[value] for value in values]
    isolation_forest = cast(
        Callable[..., _IsolationForestEstimator],
        getattr(sklearn_ensemble, "IsolationForest"),
    )
    estimator = isolation_forest(
        contamination=contamination,
        random_state=42,
    )
    estimator.fit(feature_matrix)
    raw_predictions = estimator.predict(feature_matrix)
    raw_scores = estimator.score_samples(feature_matrix)
    predictions = [_coerce_int(label) for label in raw_predictions]
    scores = [_coerce_float(score) for score in raw_scores]

    expected_value = sum(values) / len(values) if values else 0.0
    score_magnitudes = [abs(score) for score in scores]
    score_mean = sum(score_magnitudes) / len(score_magnitudes) if score_magnitudes else 0.0
    score_variance = (
        sum((score - score_mean) ** 2 for score in score_magnitudes) / len(score_magnitudes)
        if score_magnitudes
        else 0.0
    )
    score_std = sqrt(score_variance)

    anomalies: list[AnomalyPoint] = []
    for index, observation in enumerate(observations):
        if predictions[index] != -1:
            continue
        magnitude = abs(scores[index])
        if score_std > 0.0:
            z_score = abs(magnitude - score_mean) / score_std
        elif magnitude > 0.0:
            z_score = float("inf")
        else:
            z_score = 0.0
        deviation = abs(observation.value - expected_value)
        anomalies.append(
            AnomalyPoint(
                observed_at=observation.observed_at,
                observed_value=observation.value,
                expected_value=expected_value,
                deviation=deviation,
                z_score=z_score,
            )
        )
    return anomalies


def _infer_period(length: int) -> int:
    if length >= 14:
        return 7
    if length >= 8:
        return 4
    return 2


def _is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def _coerce_float(value: object) -> float:
    """Coerce third-party numeric values into plain floats."""

    if isinstance(value, (float, int)):
        return float(value)
    if hasattr(value, "__float__"):
        return float(cast(SupportsFloat, value))
    raise TypeError("Expected a numeric value convertible to float.")


def _coerce_int(value: object) -> int:
    """Coerce third-party integer labels into plain ints."""

    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if hasattr(value, "__int__"):
        return int(cast(SupportsInt, value))
    raise TypeError("Expected a numeric value convertible to int.")


def _mean(observations: list[TimeSeriesObservation]) -> float:
    return sum(observation.value for observation in observations) / len(observations)


def _standard_deviation(observations: list[TimeSeriesObservation], mean_value: float) -> float:
    variance = sum((observation.value - mean_value) ** 2 for observation in observations) / len(observations)
    return sqrt(variance)


__all__ = ["TimeseriesService", "create_timeseries_service"]
