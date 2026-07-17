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
| CMS pack gaps | **Fix both in B2 (config-only).** B2 adds `observations` mappings for the claims feeds *and* a minimal `peer_stats` block to `medicare_fraud_cms_desynpuf.yaml`, so live verification exercises the joint risk profile (z-scores + anomaly signals) on 1% TN. D1 tunes values later. |

## 3. Design

### 3.1 Config surface (new)

`TimeseriesAnalyticsConfig` on `DomainConfig` under a new `timeseries:` key:

```yaml
timeseries:
  enabled: true
  metrics:
    - metric_name: claim_payment_amount    # must match an observations mapping
      detection_strategy: z_score          # existing DetectionStrategy literal
      baseline_window: 6
      min_history: 8
      z_threshold: 2.5
      signal_weight: 0.8
```

- `TimeseriesMetricSpec` fields: `metric_name` (str), `detection_strategy`
  (existing `DetectionStrategy` literal, default `z_score`),
  `baseline_window`/`min_history`/`z_threshold` (bounded ints/floats with
  the same defaults the service models already carry), `signal_weight`
  (0–1, default 1.0).
- The stage runs only when `capabilities.timeseries` is true **and**
  `timeseries.enabled` is true **and** ≥ 1 metric is configured. No new
  adapter literals (Architecture Rule: roadmap adapters stay out of
  `DomainConfig`).
- Config loader validation: reject a `TimeseriesMetricSpec.metric_name` that
  no feed's `observations` mapping produces (fail fast at load, mirroring
  existing cross-reference checks).

### 3.2 Per-entity series source (delivers analytics.06)

New `ObservationTimeSeriesHistorySource` in
`backend/analytics/timeseries/adapters/observations.py` implementing the
existing `TimeSeriesHistorySourceProtocol`:

- `load_series(kb, entity_id, metric_name, …)` selects from the
  `observations` hypertable keyed `(knowledge_base_id, entity_id,
  metric_name)` ordered by `observed_at`.
- `entity_metric_history` remains the graph-scope path via the existing
  `PostgresTimeSeriesHistorySource`; selection between them is by call-site
  wiring (worker stage + entity route use the observations source; the
  metric-range route keeps the graph-scope source), not a config literal —
  the two sources answer different questions and are never interchangeable
  at runtime. The analytics.06 AC's `timeseries_source` config literal is
  superseded by this ruling; the cross-edge contract (per-entity reads
  `observations`, graph-scope reads `entity_metric_history`) is documented
  in `backend/analytics/README.md`.
- In-memory counterpart for tests reuses the existing
  `InMemoryTimeSeriesHistorySource` seeded through the same protocol.

### 3.3 Pipeline stage

`run_timeseries_stage` in `backend/agent/coordinator.py`, invoked inside
`handle_records_ingested` **between** the peerstats computation and
`assess_entities` (today `coordinator.py:2845-2872`), inside the same
best-effort `except Exception` envelope — the stage can never break ingest.

Per affected entity (the batch's upserted entities) × configured metric
whose `metric_name` the triggering feed maps:

1. Load the entity's series from `ObservationTimeSeriesHistorySource`.
2. Skip silently-but-logged when history < `min_history` (mirrors the
   controlled-skip pattern B1 established for insufficient graphs).
3. `TimeseriesService.analyze` with the spec's strategy/parameters.
4. Persist each `AnomalyPoint` to `timeseries_anomalies` (§3.4).
5. Write one `DerivedRiskSignal` per metric with ≥ 1 anomaly:
   `metric_name = "timeseries_anomaly:<metric>"`, `signal_value` =
   max-severity anomaly z mapped through the existing
   `z_to_signal(z, direction="high", z_cap)` bound, `weight =
   signal_weight`, rationale naming the strategy, window, and anomaly
   count. Upsert key `(kb, entity_id, metric_name, interval_start)` — the
   existing `entity_derived_signals` conflict key — with `interval_start` =
   the latest anomalous `observed_at` truncated to the UTC day (a fixed
   bucket independent of peerstats configuration, so the key is stable in
   packs that configure timeseries without peerstats).
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
  `ApiState.get_timeseries` onto the real path: series from the
  observations source, `is_anomaly` per point by membership in persisted
  `timeseries_anomalies` rows. Metric selection: the first configured
  `timeseries.metrics` entry that has data for the entity (falling back to
  the entity's first mapped observation metric when no timeseries config
  exists — keeps housing/food charts alive); no new query parameter, so
  the route signature stays identical. U2 may add explicit metric
  selection later. **`EntityTimeseriesResponse` shape is unchanged** (`backend/api/contracts.py:379`) → no OpenAPI/codegen churn,
  no frontend edits; the existing workbench chart immediately renders
  pipeline-produced anomalies. The seeded `ApiState` timeseries path is
  deleted (housing/food packs keep working — they map observations).
- `GET /analytics/timeseries` (metric-range) keeps its graph-scope
  semantics but is wired to `PostgresTimeSeriesHistorySource` instead of
  the always-empty in-memory source.

### 3.6 CMS pack changes (config-only)

`backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`:

- `observations` mappings on the claims feeds (carrier/inpatient/outpatient
  payment amounts — exact fields chosen at plan time from the feed
  `record_schema`).
- A minimal `peer_stats` block (provider-peer z-scores over claim payment
  aggregates) so risk's ≥ 2-signal floor is clearable on 1% TN.
- A `timeseries:` block per §3.1 targeting the mapped metrics.

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
- Integration (Postgres, standard `chili_test` fixture): observations
  source `load_series`; anomaly-store round-trip incl. `delete_by_kb`;
  request-level `/analytics/timeseries/{entity_id}` returning seeded
  Postgres rows (analytics.07 AC).
- Gates: pyright strict 0, ruff clean, coverage ≥ 85%, `head.sql` regen,
  no contract drift (shape unchanged — assert via codegen no-op).
- Live (controller, `make dev` + 1% TN): worker logs show the stage;
  `timeseries_anomalies` and `timeseries_anomaly:*` derived-signal rows
  exist; risk profile carries both signal families; workbench chart renders
  real anomalies; KB delete removes anomaly rows.

## 7. Backlog reconciliation at closeout

- analytics.06 — done via §3.2 (note the superseded config-literal AC and
  the documented ruling).
- analytics.07 — done via §3.5.
- Record the CMS pack's new peerstats/observations coverage where the
  module backlogs reference the pack's gaps; update
  `docs/project/planning/backlog.md` BL-047 row.
