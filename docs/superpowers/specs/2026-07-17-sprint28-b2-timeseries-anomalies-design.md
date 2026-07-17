# Sprint 2026-28 B2 — Ingest-Triggered Timeseries Anomaly Detection (Design)

**Date:** 2026-07-17
**Story:** BL-047 (B2) — timeseries anomaly detection into the ingest pipeline
(analytics.06 + analytics.07 + the pipeline-stage slice of the sprint design
note §3.1 B2).
**Status:** approved design, pre-plan
**Parent design note:** `docs/superpowers/specs/2026-07-16-sprint28-cms-fraud-workbench-design.md`

## 1. Current state (code-verified 2026-07-17 against prod @ 4995ee5)

- **Detection algorithms exist and are tested but have no production
  trigger.** `TimeseriesService` dispatches three strategies —
  `z_score` (pure Python), `stl_decomposition` (statsmodels),
  `isolation_forest` (sklearn) — on
  `TimeseriesAnalysisRequest.detection_strategy`
  (`backend/analytics/timeseries/service.py:168-195`). `analyze()` publishes
  `TimeseriesAnalyzedEvent` but no worker handler or router consumes it.
- **The workbench chart renders seeded demo data.** `useTimeseries` →
  `GET /analytics/timeseries/{entity_id}` → `ApiState.get_timeseries`
  (`backend/api/state.py:136-173`), a hardcoded in-memory series with
  hardcoded z-score parameters. The metric-range route
  (`GET /analytics/timeseries`) is wired to an always-empty
  `InMemoryTimeSeriesHistorySource` (`backend/api/dependencies.py:1268-1279`).
- **`PostgresTimeSeriesHistorySource` is unwired and graph-scope only.** It
  reads the `entity_metric_history` hypertable, which Flow B writes solely
  with `entity_id="__graph__"` graph metrics (`entity_count`,
  `relationship_count`, `avg_degree`).
- **Per-entity series already land in the `observations` hypertable.**
  `handle_records_ingested` runs `map_observations` →
  `observation_writer.write_observations` per feed
  (`backend/agent/coordinator.py:2817-2826`), keyed
  `(knowledge_base_id, entity_id, metric_name, observed_at)`. The timeseries
  module does not read them.
- **Anomalies are never persisted.** No table, no repository; the entity
  route recomputes per request against seeded data.
- **Signal stores split by consumer.** Peerstats z-scores →
  `entity_derived_signals` → `PostgresRiskSignalSource.load_profile` → risk
  scoring (requires ≥ 2 signals, `backend/analytics/risk/service.py:63`) →
  `RiskScoredEvent` → monitoring. Monitoring's own observation path
  threshold-evaluates `observations` rows. Anomaly output currently reaches
  neither.
- **No timeseries config surface.** `DomainConfig` has only the boolean
  `capabilities.timeseries`; no section maps feeds/metrics to detection.
- **The CMS DE-SynPUF pack declares neither `peer_stats` nor `observations`
  mappings**, so on the demo data peerstats computes nothing, monitoring's
  observation path receives nothing, and risk never clears its 2-signal
  floor (root cause of B1's "risk has no signals" workaround, commit
  9c8df00). The housing and food packs do declare `observations` mappings.

## 2. Owner rulings (2026-07-17 Q&A)

| Question | Ruling |
|---|---|
| Where does anomaly output land? | **Derived signals → risk.** Anomaly severities are written to `entity_derived_signals` alongside peerstats z-scores, joining the same risk-profile → `RiskScoredEvent` → alerting path. Anomaly *points* are additionally persisted to a new `timeseries_anomalies` table for the chart. Monitoring is not fed directly (no double-alerting). |
| CMS pack gaps | **Fix both in B2 (config-only).** B2 adds the timeseries metric config *and* a minimal `peer_stats` block to `medicare_fraud_cms_desynpuf.yaml`, so live verification exercises the joint risk profile (z-scores + anomaly signals) on 1% TN. D1 tunes values later. *(Amended 2026-07-17: no `observations` mappings — see the series-source re-ruling below.)* |
| Series source (amendment, 2026-07-17) | **Record aggregates, not observations.** Plan-time evidence rejected the observations-backed series: `MonitoringObservation.score` is hard-bounded [0,1] with load-time provability (payment fields have no `max_value`), `observed_at` is pinned to `ingested_at` (a bulk demo ingest collapses the time axis), and the `(kb, entity, metric, observed_at)` PK + `ON CONFLICT DO NOTHING` silently drops same-day duplicate claims. Instead the anomaly stage reads per-entity, per-interval aggregates from `raw_records` via the existing peerstats `RecordColumnSourceProtocol.load_interval_aggregates` SQL — real claim-date axis, unbounded values, no lossy collisions. `observations` remains monitoring-only. |
| Housing chart | **Add a housing `timeseries:` block** (config-only, over its existing `bah_rates` feed) so the workbench chart serves real data there after the seeded demo path is deleted. |

## 3. Design

### 3.1 Config surface (new)

`TimeseriesAnalyticsConfig` on `DomainConfig` under a new `timeseries:` key:

```yaml
timeseries:
  metrics:
    - name: weekly_carrier_billing_self    # series identity (metric_name)
      record_type: carrier_claim_record    # which feed's records feed the series
      entity_type: provider
      entity_id_field: PRF_PHYSN_NPI_1
      value_column: LINE_NCH_PMT_AMT_1
      aggregation: sum                     # sum|mean|count|max|min (peerstats literal)
      interval: week                       # day|week|month
      time_column: CLM_FROM_DT
      detection_strategy: z_score          # existing DetectionStrategy literal
      baseline_window: 4
      min_history: 6
      z_threshold: 2.5
      z_cap: 4.0
      signal_weight: 0.8
```

- `TimeseriesMetricSpec` fields *(amended 2026-07-17 per the series-source
  re-ruling)*: the aggregate identity mirrors `PeerMetricSpec`
  (`name`, `record_type`, `entity_type`, `entity_id_field`, `value_column`,
  `aggregation`, `interval`, `time_column`) plus detection knobs
  (`detection_strategy` default `z_score`, `baseline_window`, `min_history`,
  `z_threshold`, `z_cap`, `signal_weight`). `min_history` must exceed
  `baseline_window` (validated at load, mirroring the request model).
- The stage runs only when `capabilities.timeseries` is true **and** ≥ 1
  metric is configured. No new adapter literals (Architecture Rule: roadmap
  adapters stay out of `DomainConfig`).
- Cross-reference validation in `DomainConfig._validate_cross_references`:
  each spec's `record_type` must match a feed, and its
  `entity_id_field`/`value_column`/`time_column` must exist in that feed's
  `record_schema` (`value_column` numeric; `time_column` date/datetime).

### 3.2 Per-entity series source *(amended 2026-07-17: record aggregates)*

New `backend/analytics/timeseries/adapters/record_aggregates.py`:

- `load_entity_series_map(column_source, knowledge_base_id, spec) ->
  dict[str, TimeSeriesSeries]` — one `load_interval_aggregates` call per
  spec (reusing the peerstats `RecordColumnSourceProtocol` and its tested
  JSONB aggregation SQL via a `to_peer_spec()` conversion), grouped into
  per-entity series ordered by `interval_start`. The worker stage uses this
  batch form (one query per spec per ingest, not per entity).
- `RecordAggregateTimeSeriesSource(column_source, specs)` implementing
  `TimeSeriesHistorySourceProtocol.load_series` for the API entity route
  (single-entity reads); `load_metric_range` returns `[]` (per-entity
  source; graph-scope ranges are `entity_metric_history`'s job).
- The intra-`analytics` import (timeseries → peerstats adapter protocol) is
  deliberate and documented: both are submodules of the one `analytics`
  module; the alternative (duplicating the aggregation SQL) violates DRY.
- `entity_metric_history` remains the graph-scope path via the existing
  `PostgresTimeSeriesHistorySource` on the metric-range route. The
  cross-edge contract (per-entity series come from `raw_records`
  aggregates; graph-scope reads `entity_metric_history`; `observations`
  is monitoring-only) is documented in `backend/analytics/README.md`.
- analytics.06's observations-backed AC is **superseded** by this ruling —
  record the rationale in `docs/backlog/analytics.md` at closeout.

### 3.3 Pipeline stage

`run_timeseries_stage` in `backend/agent/coordinator.py`, invoked inside
`handle_records_ingested` **between** the peerstats computation and
`assess_entities` (today `coordinator.py:2845-2872`), inside the same
best-effort `except Exception` envelope — the stage can never break ingest.

Per configured metric whose `record_type` matches the triggering feed
*(amended 2026-07-17)*:

1. Build the per-entity series map once via `load_entity_series_map`
   (one aggregate query per spec), seed an
   `InMemoryTimeSeriesHistorySource`, and construct a batch-local
   `TimeseriesService` over it.
2. Skip silently-but-logged when an entity's history < `min_history`
   (mirrors the controlled-skip pattern B1 established for insufficient
   graphs).
3. `TimeseriesService.analyze` per entity with the spec's
   strategy/parameters.
4. Persist each `AnomalyPoint` to `timeseries_anomalies` (§3.4).
5. Write one `DerivedRiskSignal` per metric with ≥ 1 anomaly:
   `metric_name = "timeseries_anomaly:<metric>"`, `signal_value` =
   max-severity anomaly z mapped through the existing
   `z_to_signal(z, direction="high", z_cap)` bound, `weight =
   signal_weight`, rationale naming the strategy, window, and anomaly
   count. Upsert key `(kb, entity_id, metric_name, interval_start)` — the
   existing `entity_derived_signals` conflict key — with `interval_start` =
   the latest anomalous bucket's `observed_at` (already interval-truncated
   by the aggregation SQL, so the key is stable independent of peerstats
   configuration).
6. The immediately-following `assess_entities` call picks the new signals up
   in the same risk pass — anomaly signals and peerstats z-scores join in
   one `RiskProfile`.

Factory: `build_timeseries_stage_dependencies` alongside the existing
`build_*` helpers — Postgres adapters when a `ConnectionProvider` exists,
in-memory otherwise (both factory sites: worker composition root and API
DI).

### 3.4 Anomaly persistence (new table)

Alembic migration `timeseries_anomalies` (plain table — anomalies are
sparse; hypertable unnecessary):

```
knowledge_base_id  text      not null
entity_id          text      not null
metric_name        text      not null
observed_at        timestamptz not null
value              double precision not null
z_score            double precision
severity           double precision not null   -- normalized 0-1
detection_strategy text      not null
correlation_id     text
detected_at        timestamptz not null default now()
PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at)
```

Upsert on the PK (re-detection refreshes severity/strategy). Index
`(knowledge_base_id, entity_id, metric_name, observed_at DESC)` is implied
by the PK. Repository `TimeseriesAnomalyStore` (protocol + Postgres +
in-memory adapters, module-standard layout) with `write_anomalies`,
`load_anomalies(kb, entity_id, metric_name, range)`, and `delete_by_kb`
— the last joins the KB-delete cascade exactly as B1's cluster store did.
Regenerate `head.sql` per the BL-042 CI migration gate.

### 3.5 API + chart (delivers analytics.07)

- `get_timeseries_history_source` DI returns the Postgres-backed
  observations source when a connection provider exists (test override hook
  per the analytics.07 AC).
- `GET /analytics/timeseries/{entity_id}` is rewired off
  `ApiState.get_timeseries` onto the real path: series from
  `RecordAggregateTimeSeriesSource`, `is_anomaly` per point by membership
  in persisted `timeseries_anomalies` rows. Metric selection *(amended
  2026-07-17)*: the first configured `timeseries.metrics` spec that has
  data for the entity; when no spec yields data the response is the
  existing `availability_status="unavailable"` shape. No new query
  parameter, so the route signature stays identical; U2 may add explicit
  metric selection later. Packs that should keep a live chart declare a
  `timeseries:` block (housing gets one — see §3.6).
  **`EntityTimeseriesResponse` shape is unchanged** (`backend/api/contracts.py:379`) → no OpenAPI/codegen churn,
  no frontend edits; the existing workbench chart immediately renders
  pipeline-produced anomalies. The seeded `ApiState` timeseries path is
  deleted (housing/food packs keep working — they map observations).
- `GET /analytics/timeseries` (metric-range) keeps its graph-scope
  semantics but is wired to `PostgresTimeSeriesHistorySource` instead of
  the always-empty in-memory source.

### 3.6 Pack changes (config-only) *(amended 2026-07-17)*

`backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`:

- A minimal `peer_stats` block (provider-peer z-scores over
  `LINE_NCH_PMT_AMT_1`/`CLM_PMT_AMT` aggregates, `time_column` claim dates)
  plus `capabilities.peer_stats: true`, so risk's ≥ 2-signal floor is
  clearable on 1% TN.
- A `timeseries:` block per §3.1 over the same claim aggregates
  (self-history anomalies complementing the cross-sectional peer z-scores).
- No `observations` mappings (superseded — see §2).

`backend/config/defaults/department_air_force_housing.yaml`:

- A `timeseries:` block over the `bah_rates` feed
  (`affordability_index`, `aggregation: mean`, `time_column:
  snapshot_date`) so the workbench chart stays live after the seeded demo
  path is deleted; enable `capabilities.timeseries` if not already set.

D1 owns demo-tuning of thresholds/weights; B2 only needs the path live.

## 4. Error handling

- Stage envelope: best-effort, log-and-continue (matches peerstats).
- Insufficient history → controlled skip with a structured log line (B1
  precedent), never an exception.
- STL/isolation-forest import failures (`analytics` extra missing) →
  per-metric controlled skip logging the missing dependency; `z_score`
  never needs the extra. The backend image installs the extra (B1,
  commit b4b86a1).
- Anomaly-store write failure → logged, derived-signal write still
  attempted (the two sinks are independent).
- Route with no data → empty `points`, `availability_status="unavailable"`
  with reason, matching the existing contract fields.

## 5. Out of scope

- Forecasting/probabilistic models (analytics.08) and any new detection
  algorithms.
- Monitoring-direct anomaly observations (owner ruled risk-path only).
- UI changes — U2 owns richer anomaly markers/panels; B2's chart win comes
  free via the unchanged contract.
- Backfill of historical anomalies; detection starts with post-deploy
  ingests (re-ingest replays cover the demo).
- `entity_metric_history` per-feed record metrics (graph-scope semantics
  unchanged).

## 6. Testing & verification

- Unit: config schema validation (bad metric ref rejected), stage logic
  (skip paths, signal mapping, envelope), anomaly-store adapters, route.
- Integration (Postgres, standard `chili_test` fixture): record-aggregate
  series map over seeded `raw_records`; anomaly-store round-trip incl.
  `delete_by_kb`; request-level `/analytics/timeseries/{entity_id}`
  returning rows derived from seeded Postgres data (analytics.07 AC).
- Gates: pyright strict 0, ruff clean, coverage ≥ 85%, `head.sql` regen,
  no contract drift (shape unchanged — assert via codegen no-op).
- Live (controller, `make dev` + 1% TN): worker logs show the stage;
  `timeseries_anomalies` and `timeseries_anomaly:*` derived-signal rows
  exist; risk profile carries both signal families; workbench chart renders
  real anomalies; KB delete removes anomaly rows.

## 7. Backlog reconciliation at closeout

- analytics.06 — **superseded** (per-entity series come from `raw_records`
  aggregates, not `observations`; record the §2 rationale and close or
  re-scope the story accordingly).
- analytics.07 — done via §3.5.
- Record the CMS pack's new peerstats/observations coverage where the
  module backlogs reference the pack's gaps; update
  `docs/project/planning/backlog.md` BL-047 row.
