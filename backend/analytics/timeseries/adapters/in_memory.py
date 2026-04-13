"""In-memory time-series history source for tests and local development."""

from __future__ import annotations

from analytics.timeseries.models import TimeSeriesSeries


class InMemoryTimeSeriesHistorySource:
    """A seeded source of historical metric observations."""

    def __init__(self, series: list[TimeSeriesSeries] | None = None) -> None:
        self._series_by_key: dict[tuple[str, str, str], TimeSeriesSeries] = {}
        for series_item in series or []:
            self.put_series(series_item)

    def put_series(self, series: TimeSeriesSeries) -> None:
        self._series_by_key[_series_key(series.knowledge_base_id, series.entity_id, series.metric_name)] = series

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


def _series_key(knowledge_base_id: str, entity_id: str, metric_name: str) -> tuple[str, str, str]:
    return (knowledge_base_id, entity_id, metric_name)