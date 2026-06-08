# peerstats

Cross-sectional peer-group z-score analytics.

For each `PeerMetricSpec` in `DomainConfig.peer_stats`, this module aggregates a
record column per entity over a config interval (`day`/`week`/`month`), z-scores
each entity's interval aggregate against its peer group (`entity_type` + optional
`group_by` columns) for that interval, and writes a `DerivedRiskSignal` per entity
to the `entity_derived_signals` table. `PostgresRiskSignalSource` (in
`analytics/risk`) reads those signals so the risk service scores them — the risk
module itself is unchanged.

## Flow
1. The worker's `RecordsIngestedEvent` handler calls `run_peerstats_stage`
   (best-effort, gated on `capabilities.peer_stats`).
2. `PeerStatsService.compute` loads per-entity interval aggregates
   (`RecordColumnSourceProtocol`), computes peer mean/std (population) and z,
   maps z → `[0,1]` signal value via `direction` + `z_cap`, and persists via
   `DerivedRiskSignalWriterProtocol`. It recomputes all intervals each run
   (idempotent upsert).
3. The worker assesses the deduped set of affected entities once each, so
   `risk_score_history` and `/analytics/risk-scores` reflect the new signals.

## Adapters
- In-memory (`adapters/in_memory.py`) — tests/dev. The in-memory column source is
  empty unless seeded; real ingest data flows through the Postgres adapter.
- Postgres (`adapters/postgres.py`) — aggregates `raw_records` JSONB in SQL
  (skipping non-numeric values), upserts `entity_derived_signals`.

## Edge cases
Cohort `< min_peers` → no signal; `peer_std == 0` → `z = 0`; missing/non-numeric
value → row skipped; group membership computed per interval.

> **Two-signal floor:** the risk service requires ≥2 signals to score an entity.
> Each `PeerMetricSpec` contributes one derived signal per entity, so a domain
> must configure **at least two matching specs** for an entity type for those
> entities to receive a risk score (the medicare default ships two provider
> specs). With a single spec, affected entities are assessed but skipped with an
> INFO log (`RiskInsufficientSignalsError`) and produce no score.
