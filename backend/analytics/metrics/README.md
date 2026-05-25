# analytics/metrics

Entity-metric persistence. A small read/write package — no service, no events —
keyed to the two metric tables created by the persistence baseline migration:

- `entity_metric_history` (TimescaleDB hypertable) — graph metrics over time.
- `entity_metrics_current` — the latest value per entity metric.

## Components

- `EntityMetricRepository` (`adapters/protocols.py`) — `record_metrics` (append
  history + upsert current) and `load_current_metrics` (snapshot read).
- `InMemoryEntityMetricRepository` / `PostgresEntityMetricRepository` — config-
  selected siblings; the Postgres adapter depends only on
  `database.ConnectionProvider`.
- `MetricsRecomputeThrottle` (`throttle.py`) — per-knowledge-base rate limiter.
  Flow 2 (`agent.coordinator.handle_graph_updated_for_analytics`) consults it so
  a burst of `GraphUpdatedEvent`s cannot trigger a metric-recompute storm.
- Graph-scope metrics use the sentinel `entity_id = "__graph__"` with metric
  names `entity_count`, `relationship_count`, `avg_degree`.

## Adapter selection

`config.database.backend`: `in_memory` (default, used by tests) → in-memory
adapter; `postgres` → `PostgresEntityMetricRepository`. Selection happens in the
worker composition root (`agent/coordinator.py::build_entity_metric_repository`).
