"""Per-entity time series derived from raw_records interval aggregates.

Reuses the peerstats record-column aggregation SQL through
``RecordColumnSourceProtocol`` — a deliberate intra-``analytics`` dependency
(both are submodules of the one analytics module; duplicating the JSONB
aggregation here would violate DRY). Peerstats reads these aggregates
cross-sectionally; this source reads them longitudinally per entity.
"""

from __future__ import annotations

from datetime import datetime

from analytics.peerstats.adapters.protocols import RecordColumnSourceProtocol
from analytics.timeseries.models import TimeSeriesObservation, TimeSeriesSeries
from config.schema import PeerMetricSpec, TimeseriesMetricSpec


def to_peer_spec(spec: TimeseriesMetricSpec) -> PeerMetricSpec:
    """Express a timeseries spec as the aggregate identity peerstats loads."""

    return PeerMetricSpec(
        name=spec.name,
        record_type=spec.record_type,
        entity_type=spec.entity_type,
        entity_id_field=spec.entity_id_field,
        value_column=spec.value_column,
        aggregation=spec.aggregation,
        interval=spec.interval,
        time_column=spec.time_column,
    )


def load_entity_series_map(
    column_source: RecordColumnSourceProtocol,
    *,
    knowledge_base_id: str,
    spec: TimeseriesMetricSpec,
) -> dict[str, TimeSeriesSeries]:
    """One aggregate query, grouped into ordered per-entity series."""

    aggregates = column_source.load_interval_aggregates(
        knowledge_base_id=knowledge_base_id,
        spec=to_peer_spec(spec),
        interval_starts=[],
    )
    observations_by_entity: dict[str, list[TimeSeriesObservation]] = {}
    for aggregate in aggregates:
        observations_by_entity.setdefault(aggregate.entity_id, []).append(
            TimeSeriesObservation(
                observed_at=aggregate.interval_start,
                value=aggregate.aggregate_value,
            )
        )
    series_map: dict[str, TimeSeriesSeries] = {}
    for entity_id, observations in observations_by_entity.items():
        observations.sort(key=lambda observation: observation.observed_at)
        series_map[entity_id] = TimeSeriesSeries(
            knowledge_base_id=knowledge_base_id,
            entity_id=entity_id,
            metric_name=spec.name,
            observations=observations,
        )
    return series_map


class RecordAggregateTimeSeriesSource:
    """A ``TimeSeriesHistorySourceProtocol`` over raw_records aggregates."""

    def __init__(
        self,
        column_source: RecordColumnSourceProtocol,
        *,
        specs: list[TimeseriesMetricSpec],
    ) -> None:
        self._column_source = column_source
        self._specs_by_name: dict[str, TimeseriesMetricSpec] = {
            spec.name: spec for spec in specs
        }

    def metric_names(self) -> list[str]:
        """Configured series names in declaration order."""

        return list(self._specs_by_name)

    def load_series(
        self,
        *,
        knowledge_base_id: str,
        entity_id: str,
        metric_name: str,
    ) -> TimeSeriesSeries:
        spec = self._specs_by_name.get(metric_name)
        if spec is None:
            raise ValueError(f"No timeseries metric spec named '{metric_name}'.")
        series_map = load_entity_series_map(
            self._column_source, knowledge_base_id=knowledge_base_id, spec=spec
        )
        series = series_map.get(entity_id)
        if series is None:
            raise ValueError(
                "No time series registered for "
                f"knowledge_base_id='{knowledge_base_id}', "
                f"entity_id='{entity_id}', metric_name='{metric_name}'."
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
        # Per-entity source; graph-scope metric ranges are
        # entity_metric_history's job (PostgresTimeSeriesHistorySource).
        return []


__all__ = [
    "RecordAggregateTimeSeriesSource",
    "load_entity_series_map",
    "to_peer_spec",
]
