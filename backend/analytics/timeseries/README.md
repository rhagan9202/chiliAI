# analytics/timeseries

Self-history anomaly detection: compare an entity's metric against its own
interval history and flag the buckets that deviate. `TimeseriesService` runs
one of three detection strategies over a loaded series and publishes
`TimeseriesAnalyzedEvent`; the worker turns detected anomalies into persisted
`timeseries_anomalies` rows and into derived risk signals that
`analytics/risk` scores.

The series-source split (per-entity series from `raw_records` aggregates,
graph-scope series from `entity_metric_history`, `observations` never read) is
documented in the package guide,
[`../README.md` § Timeseries series-source contract](../README.md#timeseries-series-source-contract);
this file does not repeat it.

## Layout

| File | Responsibility |
|------|----------------|
| `models.py` | `TimeSeriesObservation`, `TimeSeriesSeries`, `AnomalyPoint`, `TimeSeriesAnalysisResult`, `TimeseriesAnomalyRecord` (persisted row). |
| `service_models.py` | `TimeseriesAnalysisRequest` / `TimeseriesAnalysisResponse` / `TimeseriesAnomaly`, `TimeseriesQueryRequest` / `MetricTimeseriesResponse` / `TimeseriesPoint`. |
| `protocols.py` | `TimeseriesServiceProtocol` — `analyze`, `query_metric`. |
| `service.py` | `TimeseriesService` / `create_timeseries_service`; detection helpers `_detect_anomalies` (z-score), `_detect_anomalies_stl`, `_detect_anomalies_isolation_forest`. |
| `adapters/protocols.py` | `TimeSeriesHistorySourceProtocol` (`load_series`, `load_metric_range`) and `TimeseriesAnomalyStoreProtocol` (`write_anomalies`, `load_anomalies`, `delete_by_kb`). |
| `adapters/record_aggregates.py` | `RecordAggregateTimeSeriesSource`, `load_entity_series_map`, `to_peer_spec` — per-entity series built on `analytics/peerstats`'s interval-aggregate query. |
| `adapters/postgres.py` | `PostgresTimeSeriesHistorySource` (`entity_metric_history`), `PostgresTimeseriesAnomalyStore` (`timeseries_anomalies`). |
| `adapters/in_memory.py` | `InMemoryTimeSeriesHistorySource`, `InMemoryTimeseriesAnomalyStore`. |
| `exceptions.py` | `TimeseriesError` and subclasses `TimeseriesConfigurationError`, `TimeseriesInsufficientHistoryError`, `TimeseriesSourceError`. |

## Contracts and invariants

- `detection_strategy` is `z_score` (default), `stl_decomposition`
  (statsmodels) or `isolation_forest` (scikit-learn). The optional libraries
  are imported lazily; when missing, `analyze` raises
  `TimeseriesConfigurationError`. Both come from the `analytics` extra.
- `min_history` must exceed `baseline_window` (validated on both
  `TimeseriesAnalysisRequest` and `TimeseriesMetricSpec`). A series shorter
  than `min_history`, after optional `window_size` trimming, raises
  `TimeseriesInsufficientHistoryError`.
- The service itself persists nothing; anomaly rows and risk signals are
  written by the worker stage below.

## How it is reached

- **Worker:** `agent/coordinator.py::run_timeseries_stage`, called from the
  records-ingested handler when `capabilities.timeseries` is on and
  `DomainConfig.timeseries.metrics` (`TimeseriesAnalyticsConfig` /
  `TimeseriesMetricSpec`) has specs for the feed's `record_type`. It runs one
  aggregate query per spec, analyzes each entity over an in-memory source,
  skips entities with insufficient history, stops a spec on a configuration
  error, then writes `TimeseriesAnomalyRecord`s to the anomaly store and one
  `DerivedRiskSignal` per affected entity (`metric_name =
  "timeseries_anomaly:<spec name>"`, `peer_group_key = "__self_history__"`).
  The affected entity ids are returned so the caller re-assesses their risk.
- **API** (`api/routers/analytics.py`, prefix `/analytics`, viewer):
  `GET /timeseries/{entity_id}` returns the first configured metric with data
  for the entity, marking points that match a stored anomaly
  (`api/dependencies.py::get_timeseries_payload`); `GET /timeseries` is the
  graph-scope metric-range read through `query_metric`.

## Persistence

| Table | Migration | Access |
|-------|-----------|--------|
| `timeseries_anomalies` | `0011_timeseries_anomalies` | `PostgresTimeseriesAnomalyStore`; removed on KB deletion by the `timeseries_anomalies` step in `knowledgebases/cleanup.py`. |
| `entity_metric_history` | `0001_persistence_baseline` | Read-only here, by `PostgresTimeSeriesHistorySource`. |
| `raw_records` | (records module) | Read-only, through the peerstats aggregate query. |

Derived signals land in `entity_derived_signals`, which `analytics/peerstats`
owns (see [`../peerstats/README.md`](../peerstats/README.md)).

## Current gaps (from `TODO(production)` in code)

- `TimeSeriesHistorySourceProtocol` has no date-range-filtered or multi-entity
  `load_series`.

## Tests

`tests/analytics/timeseries/` — models, service (all three strategies),
in-memory adapters, record-aggregate source, anomaly stores, and the Postgres
history source and anomaly store.
