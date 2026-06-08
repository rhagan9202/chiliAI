# Design: Config-Driven Peer-Group Z-Scores → Risk Signals

**Date:** 2026-06-08
**Status:** Approved (design); pending implementation plan
**Author:** brainstorming session (Ron Hagan + Claude)

## Problem

chiliAI ingests structured records (`raw_records` JSONB) and has a working risk
service that scores entities from weighted `RiskSignal`s. But **nothing constructs
real risk signals from records at runtime** — the only `RiskSignalSource` is an
in-memory, hand-seeded fixture in `ApiState`. There is also no cross-sectional
peer-group statistics: the existing `analytics/timeseries/` module computes
z-scores **temporally** (an entity vs. its *own* rolling history), not against a
cohort of peers.

This design adds a config-driven capability that:

1. Takes parameters and columns of interest from the domain config.
2. Reads those columns from the persistent records database (`raw_records`).
3. Forms a per-entity timeseries of aggregate values over config-specified intervals.
4. Computes z-scores for each entity's interval aggregate against its **peer group**
   for that interval.
5. Feeds those z-scores into the risk score as `RiskSignal`s.

## Goals / Non-Goals

**Goals**
- Cross-sectional peer-group z-score computation, driven entirely by `DomainConfig`
  (no code change to add a new metric/column).
- Persist derived signals so the `/analytics/risk-scores/{entity_id}` endpoint
  reflects real records-driven z-scores.
- Leave the `risk/` module's scoring logic untouched — it still only consumes
  `RiskSignal`s.

**Non-Goals (out of scope)**
- Frontend UI for configuring metric specs (existing risk/timeseries contracts
  already render the resulting scores; no contract change).
- Backfill of historical intervals beyond those touched by the current ingest batch.
- Percentile-rank or other robust alternatives to z-scores.
- Scheduled/periodic recompute (trigger is per-ingest only).

## Architecture Decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Peer-group definition | `entity_type` + optional config grouping columns; defaults to type-wide when no grouping columns configured |
| Aggregation grain | Per-entity aggregate per interval, configurable function (sum/mean/count/max/min); multiple `(column, aggregation, interval)` specs allowed |
| Z → RiskSignal mapping | Config-declared `direction` (high / low / two_sided) + `z_cap` + `weight`; `signal_value = clamp(z/z_cap, 0..1)` on the risky tail |
| Module placement / trigger | New `analytics/peerstats/` module; triggered by `RecordsIngestedEvent` (after observations are written) |
| Risk wiring | Persist derived signals to a new table; new Postgres-backed `RiskSignalSource` assembles `RiskProfile`s from them |

## End-to-End Data Flow

```
RecordsIngestedEvent (existing)
  └─ worker handle_records_ingested (existing: maps entities, writes observations)
        └─ NEW peerstats stage (gated on capabilities.peer_stats; best-effort)
              1. For each PeerMetricSpec, determine the interval buckets touched by this batch.
              2. PeerStatsService.compute(kb_id, spec, interval_starts):
                   a. Load interval population from raw_records — ALL entities in the
                      cohort for those intervals, not just the incoming batch.
                   b. Per entity: aggregate value_column over the interval (sum/mean/count/max/min).
                   c. Per peer group (entity_type [+ group_by col values]) per interval:
                      compute mean, std (population).
                   d. Per entity: z = (aggregate - peer_mean) / peer_std.
                   e. Map z → signal_value via direction + z_cap; attach weight.
                   f. Persist rows to entity_derived_signals (incl. peer_mean/std/z for audit).
              3. Collect the DEDUPED set of affected entity ids across all specs/intervals,
                 then assess them in batches (not one event per entity):
                   - for each unique entity: RiskService.assess(entity)
                     - PostgresRiskSignalSource.load_profile reads latest derived signals → RiskProfile
                     - LinearScoringStrategy sums weighted signals → overall_score (risk module UNCHANGED)
                     - publishes RiskScoredEvent → risk_score_history (existing Flow 3)
```

The risk module is not modified — this design fills the empty "where do real
signals come from" slot upstream of it.

## Components

### 1. Config additions — `backend/config/schema.py`

New capability flag on `CapabilitiesConfig`:

```python
peer_stats: bool = False
```

New models, referenced from `DomainConfig` as `peer_stats: PeerStatsConfig | None = None`:

```python
class PeerMetricSpec(BaseModel):
    name: str                       # signal_name surfaced in risk factors
    record_type: str                # which RecordFeedConfig feed to read
    entity_type: str                # entity the signal attaches to
    entity_id_field: str            # payload field → entity id
    value_column: str               # column of interest in payload
    aggregation: Literal["sum", "mean", "count", "max", "min"]
    interval: Literal["day", "week", "month"]
    time_column: str | None = None  # payload date col for bucketing; falls back to ingested_at
    group_by: list[str] = Field(default_factory=list)  # extra cohort cols; [] = entity-type-wide
    direction: Literal["high", "low", "two_sided"] = "high"
    z_cap: float = Field(default=4.0, gt=0.0)
    weight: float = Field(default=1.0, gt=0.0)
    min_peers: int = Field(default=5, ge=2)            # cohort smaller than this → no signal
    rationale_template: str = "{name}: z={z:.2f} vs {peer_group} peers"

class PeerStatsConfig(BaseModel):
    metrics: list[PeerMetricSpec] = Field(default_factory=list)
```

The medicare default YAML (`config/defaults/medicare_fraud.yaml`) gains
`capabilities.peer_stats: true` and ≥2 specs (e.g. weekly `SUM(billed_amount)`
per provider, and weekly `COUNT` of claims per provider) so the risk service's
≥2-signal requirement is satisfied for the exemplar domain.

### 2. New module — `backend/analytics/peerstats/`

Standard module layout (protocols / models / service_models / service / adapters / exceptions).

- **`models.py`** — internal domain models:
  - `PeerAggregate` — one entity's aggregate for one interval bucket:
    `entity_id`, `entity_type`, `peer_group_key`, `interval_start`, `aggregate_value`.
  - `PeerGroupStat` — `peer_group_key`, `interval_start`, `mean`, `std`, `count`.
  - `DerivedRiskSignal` — `entity_id`, `entity_type`, `metric_name`, `interval_start`,
    `peer_group_key`, `aggregate_value`, `peer_mean`, `peer_std`, `z_score`,
    `signal_value` (∈[0,1]), `weight`, `rationale`, `correlation_id`.

- **`service_models.py`** — `PeerStatsComputeRequest` (`knowledge_base_id`,
  `spec`, `interval_starts`, `correlation_id`), `PeerStatsComputeResponse`
  (`metric_name`, `signals_written`, `affected_entity_ids: list[str]`). The worker
  unions `affected_entity_ids` across all `compute` calls into a deduped set before
  the assess pass.

- **`protocols.py`** — `PeerStatsServiceProtocol.compute(request) -> PeerStatsComputeResponse`.

- **`adapters/protocols.py`**:
  - `RecordColumnSourceProtocol.load_interval_aggregates(kb_id, spec, interval_starts) -> list[PeerAggregate]`
    — the Postgres impl queries `raw_records`, casting `(payload->>value_column)::numeric`,
    bucketing with `date_trunc(interval, time_col)` (where `time_col` is
    `(payload->>time_column)::timestamptz` or `ingested_at` fallback), and grouping
    `BY entity_id, bucket, group_key`. The in-memory impl performs the same
    aggregation in Python for tests.
  - `DerivedRiskSignalWriterProtocol.write_signals(rows: list[DerivedRiskSignal]) -> int`.

- **`service.py`** — `PeerStatsService.compute`:
  - SQL/adapter returns per-entity-per-interval aggregates.
  - **All statistics (mean/std/z) computed in Python** so the in-memory and Postgres
    paths share logic and the math is directly unit-testable.
  - z → signal mapping: `high` → `clamp(z / z_cap, 0, 1)` (positive tail only);
    `low` → `clamp(-z / z_cap, 0, 1)`; `two_sided` → `clamp(abs(z) / z_cap, 0, 1)`.
  - Emits a `PeerStatsComputedEvent` (lightweight, for observability/audit).

- **`exceptions.py`** — `PeerStatsConfigurationError`, etc.

- **`adapters/in_memory.py`** — `InMemoryRecordColumnSource`,
  `InMemoryDerivedRiskSignalWriter` for tests/dev.
- **`adapters/postgres.py`** — `PostgresRecordColumnSource`,
  `PostgresDerivedRiskSignalWriter`.

### 3. Persistence — new Alembic migration

`entity_derived_signals`:

```
knowledge_base_id text             NOT NULL
entity_id         text             NOT NULL
entity_type       text             NOT NULL
metric_name       text             NOT NULL
interval_start    timestamptz      NOT NULL
peer_group_key    text             NOT NULL
aggregate_value   double precision NOT NULL
peer_mean         double precision NOT NULL
peer_std          double precision NOT NULL
z_score           double precision NOT NULL
signal_value      double precision NOT NULL
weight            double precision NOT NULL
rationale         text             NOT NULL
correlation_id    text             NOT NULL
computed_at       timestamptz      NOT NULL DEFAULT now()

PRIMARY KEY (knowledge_base_id, entity_id, metric_name, interval_start)
INDEX ix_entity_derived_signals_latest ON
    (knowledge_base_id, entity_id, metric_name, computed_at DESC)
```

Audit columns (`peer_mean`, `peer_std`, `z_score`, `aggregate_value`) live inline —
no separate stats table (YAGNI). Writes are idempotent (`ON CONFLICT (... interval_start)
DO UPDATE`) so re-ingesting a batch recomputes cleanly.

### 4. Risk integration — `backend/analytics/risk/adapters/postgres.py`

New `PostgresRiskSignalSource` implementing the **existing** `RiskSignalSourceProtocol`:

- `load_profile(kb_id, entity_id)` → for each `metric_name`, select the latest
  `entity_derived_signals` row (by `computed_at`), build a `RiskSignal`
  (`signal_name=metric_name`, `value=signal_value`, `weight=weight`,
  `rationale=rationale`) → assemble a `RiskProfile`.
- `list_ranked_entries(...)` → reads the latest score per entity from the existing
  `risk_score_history` table.
- `load_historical_score(...)` → existing `risk_score_history` query (reuse current
  `PostgresRiskHistoryStore` query shape).

Wiring in `backend/api/dependencies.py`: `get_risk_signal_source()` returns the
Postgres source when a database is configured; the in-memory seeded source remains
the dev/test fallback. No change to `get_risk_service()` composition.

The `/analytics/risk-scores/{entity_id}` endpoint then reflects real records-driven
z-scores. Entities with `<2` signals fall through the existing graceful "unavailable"
path in `ApiState.get_risk_score` (catches `RiskInsufficientSignalsError`), so no risk
module change is needed.

### 5. Worker wiring — `backend/agent/coordinator.py`

A new best-effort stage inside `handle_records_ingested`, after observations are
written, gated on `capabilities.peer_stats`:

1. For each `PeerMetricSpec` whose `record_type` matches the ingested feed, derive
   the interval buckets touched by this batch (from the batch's records' time values).
2. Call `PeerStatsService.compute(...)` for those intervals; each call returns the set
   of entity ids it wrote signals for.
3. **Accumulate affected entity ids into a single deduped set across all specs/intervals**
   (an entity touched by N specs/intervals is assessed once), then assess them in
   bounded batches via a helper `assess_entities(kb_id, entity_ids)` rather than
   emitting one assess-and-event per (spec, interval, entity). Each unique entity's
   `RiskService.assess` still publishes one `RiskScoredEvent` so `risk_score_history`
   and the risk-scores endpoint reflect the new signals.

Failures are logged and do not break ingest (consistent with the existing best-effort
policy-evaluation stage). Dependencies (`PeerStatsService`, column source, signal
writer) are constructed in `build_worker_dependencies`.

## Edge Cases

- **Cohort `< min_peers`** → no signal emitted for that entity/interval.
- **`peer_std == 0`** (degenerate cohort) → `z = 0` (neutral signal value 0).
- **Missing or non-numeric `value_column`** in a record → that record contributes
  nothing to the aggregate (skipped); entities with no valid values produce no signal.
- **Group membership changes across intervals** → computed per interval from that
  interval's records; an entity can belong to different peer groups in different
  intervals.
- **`<2` signals for an entity** → risk assess raises `RiskInsufficientSignalsError`,
  handled by the existing "unavailable" path; medicare default ships ≥2 specs.
- **Re-ingest of the same batch** → idempotent upsert recomputes the same intervals.

## Testing & Quality Gates

- New in-memory adapters enable full unit coverage of `PeerStatsService` (aggregation
  grouping, mean/std/z math, direction mapping, clamping, min_peers, std==0).
- Postgres adapter tests under `@pytest.mark.integration` (raw_records JSONB cast +
  `date_trunc` bucketing; idempotent writes).
- `PostgresRiskSignalSource.load_profile` assembling a `RiskProfile` from derived signals.
- Worker stage test: `RecordsIngestedEvent` → derived signals persisted → entity risk
  assessed.
- Config schema validation tests for `PeerMetricSpec` / `PeerStatsConfig`.
- Gates: `pyright --strict` clean, `ruff check --no-cache`, pytest coverage ≥85% per
  package. No frontend contract changes (so no codegen), but verify OpenAPI is unchanged.

## Documentation Updates

- `backend/analytics/README.md` (or new `analytics/peerstats/README.md`) — module purpose.
- `backend/README.md` — module map + Current State.
- `docs/architecture.md` — new peerstats stage in the worker flow and the
  records → peer z-scores → risk signals path.
- `docs/testing/DATA.md` — if any new fixture data is added for tests.

## Open Questions

None outstanding — all design decisions resolved during brainstorming.
