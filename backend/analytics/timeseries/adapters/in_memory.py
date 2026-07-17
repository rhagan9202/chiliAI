"""In-memory time-series history source for tests and local development."""

from __future__ import annotations

from datetime import datetime

from analytics.timeseries.models import (
    TimeSeriesObservation,
    TimeSeriesSeries,
    TimeseriesAnomalyRecord,
)

__all__ = ["InMemoryTimeSeriesHistorySource", "InMemoryTimeseriesAnomalyStore"]


class InMemoryTimeSeriesHistorySource:
    """A seeded source of historical metric observations."""

    def __init__(
        self,
        series: list[TimeSeriesSeries] | None = None,
        *,
        metric_observations: dict[tuple[str, str], list[TimeSeriesObservation]] | None = None,
    ) -> None:
        self._series_by_key: dict[tuple[str, str, str], TimeSeriesSeries] = {}
        self._metric_observations: dict[tuple[str, str], list[TimeSeriesObservation]] = {}
        for series_item in series or []:
            self.put_series(series_item)
        for metric_key, observations in (metric_observations or {}).items():
            self.put_metric_observations(
                knowledge_base_id=metric_key[0],
                metric_name=metric_key[1],
                observations=observations,
            )

    def put_series(self, series: TimeSeriesSeries) -> None:
        self._series_by_key[_series_key(series.knowledge_base_id, series.entity_id, series.metric_name)] = series

    def put_metric_observations(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        observations: list[TimeSeriesObservation],
    ) -> None:
        ordered = sorted(observations, key=lambda observation: observation.observed_at)
        self._metric_observations[(knowledge_base_id, metric_name)] = ordered

    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        key = _series_key(knowledge_base_id, entity_id, metric_name)
        series = self._series_by_key.get(key)
        if series is None:
            raise ValueError(
                "No time series registered for "
                f"knowledge_base_id='{knowledge_base_id}', entity_id='{entity_id}', metric_name='{metric_name}'."
            )
        return series

    def load_metric_range(
        self,
        *,
        knowledge_base_id: str,
        metric_name: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeSeriesObservation]:
        observations = self._metric_observations.get((knowledge_base_id, metric_name), [])
        return [
            observation
            for observation in observations
            if start <= observation.observed_at <= end
        ]


def _series_key(knowledge_base_id: str, entity_id: str, metric_name: str) -> tuple[str, str, str]:
    return (knowledge_base_id, entity_id, metric_name)


class InMemoryTimeseriesAnomalyStore:
    """Dict-backed anomaly store keyed like the Postgres PK."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, datetime], TimeseriesAnomalyRecord] = {}

    def write_anomalies(self, records: list[TimeseriesAnomalyRecord]) -> int:
        for record in records:
            key = (
                record.knowledge_base_id,
                record.entity_id,
                record.metric_name,
                record.observed_at,
            )
            self._records[key] = record
        return len(records)

    def load_anomalies(
        self, *, knowledge_base_id: str, entity_id: str, metric_name: str
    ) -> list[TimeseriesAnomalyRecord]:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_id == entity_id
            and record.metric_name == metric_name
        ]
        return sorted(matches, key=lambda record: record.observed_at)

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys = [key for key in self._records if key[0] == knowledge_base_id]
        for key in keys:
            del self._records[key]
        return len(keys)