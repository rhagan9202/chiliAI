# Backend Persistence Architecture — Design

> **Status**: Approved design (brainstorming output). Source of truth for the
> implementation plan that follows.
> **Date**: 2026-05-14
> **Scope**: Durable persistence across the backend — a canonical store for
> structured ingested records, a time-series + tabular home for graph metrics
> and observations, and write-back of risk scores and alerts into the graph.

---

## 1. Problem Statement

chiliAI today persists three things durably: the knowledge graph (Neo4j
adapter), embeddings (Qdrant adapter), and raw files / projection artifacts
(object store). Three gaps remain:

1. **No canonical home for structured ingested data.** `ingestion/` handles
   documents only (parse → chunk → LLM-extract → entities). There is no path
   for tabular operational data (claims, observations, records) — the
   "active monitoring" half of the platform's workflow.
2. **Analytics read from in-memory adapters only.** `monitoring`,
   `analytics/timeseries`, and `analytics/risk` define `*SourceProtocol`
   contracts but ship only in-memory adapters. Their `# TODO(production)`
   notes call for adapters "sourcing from a time-series DB / graph".
3. **Analytical outcomes do not loop back.** `RiskService` and
   `MonitoringService` publish events but never persist results or write them
   onto the graph; `GraphService.compute_metrics()` returns a snapshot that is
   never stored.

This design adds a persistence backbone that closes all three gaps.

## 2. Goals

- Land structured ingested records in a durable, replayable, audited store.
- Fan structured data out to both the graph and the analytics modules.
- Persist graph metrics into a time-series store **and** a current-snapshot
  data table for further analytics processing.
- Write risk scores and alerts back into the graph (latest snapshot on the
  entity + history nodes).
- Preserve every architectural rule in `CLAUDE.md` / `docs/architecture.md`:
  protocol + adapter for every external system, cross-module interaction only
  via the API gateway / agent coordinator / shared contracts, no hardcoded
  domain types, domain reconfigurability via config.

## 3. Non-Goals

- Replacing the API's existing KB / alert / workflow projections
  (`_kb_store`, `_alert_store`, `_workflow_projection`). `alert_history` here
  is an analytics-facing log, not the frontend `/alerts` contract.
- Streaming ingestion transports (Kafka, etc.). `records/` is structured so a
  stream source can be added later, but only file-upload and api-push sources
  are in scope now.
- Timescale retention / downsampling policies. Hypertables are created; tuning
  retention is deferred and noted as future work.
- Production deployment manifests for the Timescale service beyond the dev
  compose stack.

## 4. Locked Decisions

These were settled during brainstorming and are not open for re-litigation in
the implementation plan:

| # | Decision |
|---|----------|
| D1 | Persistence engine: **Postgres + TimescaleDB** — one engine; hypertables for time-series, regular tables for relational. |
| D2 | Code layout: a new **`database/`** infra module (engine/pool/migrations) plus **per-consumer adapters** in their owning modules. |
| D3 | Tabular ingestion lives in a **new top-level `records/` module**, parallel to `ingestion/` (documents). |
| D4 | **Postgres-first**: `records/` lands canonical rows; the worker fans out to the graph and analytics. |
| D5 | Tabular records use a **generic `raw_records` table** (`record_type` + JSONB `payload`); feed schemas are declared in `DomainConfig`. |
| D6 | Graph metrics are computed **event-driven on `GraphUpdatedEvent`**. |
| D7 | Risk/alerts write back as **both** an entity-property snapshot **and** history nodes, performed by **worker coordinator handlers**. |
| D8 | Driver / query layer: **psycopg 3 (sync)** + **Alembic** with raw-SQL migrations; no ORM. |
| D9 | Flow 1 runs as a **single handler, graph-upsert-then-observations**. |

### Rationale notes

- **D1**: Postgres is already provisioned in `docker-compose.dev.yaml` with
  `DATABASE_URL` wired into `api` and `worker`; only the schema, driver, and
  config are missing. TimescaleDB adds hypertables without a second engine.
- **D8**: sync psycopg matches every other adapter in the backend (graph,
  vectorstore, storage adapters are all sync; worker handlers call sync
  services). Raw SQL keeps `pyright --strict` / no-`Any` clean and makes
  Timescale-specific DDL (`create_hypertable`) natural. SQLAlchemy Core 2.0 was
  considered and rejected: its result-row typing still leaks `Any`, and
  Timescale DDL would be raw SQL regardless.

## 5. Module Layout

### 5.1 `database/` — new infra module

Dependency-light infrastructure, analogous to `events/`. No domain knowledge,
no business logic. Imports only `config` and `shared`.

```
backend/database/
├── __init__.py
├── engine.py          # connection pool built from DatabaseConfig
├── protocols.py       # ConnectionProvider protocol
├── runtime.py         # build provider from config/env (mirrors events/runtime.py)
├── health.py          # readiness probe
├── exceptions.py      # DatabaseError hierarchy
└── migrations/        # Alembic env + versioned raw-SQL migrations (owns the schema)
    ├── env.py
    ├── alembic.ini
    └── versions/
```

- `ConnectionProvider` is the protocol consumers depend on; it hands out
  pooled connections / cursors. Consumers never import psycopg directly.
- `database/` owns the entire SQL schema through Alembic migrations, grouped
  by owning module in migration comments.

### 5.2 `records/` — new top-level module

Tabular ingestion, parallel to `ingestion/` (documents). Follows the standard
module template.

```
backend/records/
├── __init__.py
├── protocols.py        # RecordSource, RawRecordStore
├── models.py           # RawRecord, RecordBatch, RecordFeed (internal)
├── service_models.py   # RecordSubmission, RecordIngestReceipt (external)
├── service.py          # RecordsService.register_records()
├── exceptions.py
├── mappers/            # config-driven row -> Entity/Relationship/observation
│   ├── __init__.py
│   └── feed_mapper.py
└── adapters/
    ├── __init__.py
    ├── protocols.py
    ├── sources/        # CSV/JSONL file, api_push
    │   ├── __init__.py
    │   ├── file_source.py
    │   └── api_push_source.py
    ├── in_memory.py    # InMemoryRawRecordStore
    └── postgres.py     # PostgresRawRecordStore (raw_records table)
```

`RecordsService.register_records()`:
1. Validates each row against the matching `RecordFeedConfig.schema`.
2. Persists rows via `RawRecordStore` to `raw_records`.
3. Publishes `RecordsIngestedEvent`.

`records/` never imports `graph` or `analytics` internals — it communicates
downstream only by publishing events.

### 5.3 Per-consumer Postgres adapters

Each consuming module gains a Postgres adapter as a **repository-style class**
— one class exposes the existing read protocol *and* the new write methods —
sitting beside the existing in-memory adapter. The in-memory adapters remain
the local/test backend; Postgres adapters are config-selected siblings,
mirroring how the Neo4j adapter sits next to the in-memory graph adapter.

| Module | New file | Implements | Backing table(s) |
|--------|----------|-----------|------------------|
| `monitoring` | `adapters/postgres.py` | `ObservationSourceProtocol` (read) + observation writer | `observations` |
| `analytics/timeseries` | `adapters/postgres.py` | `TimeSeriesHistorySourceProtocol` (read) | `entity_metric_history`, `observations` |
| `analytics/risk` | `adapters/postgres.py` | `RiskSignalSourceProtocol` (read) + risk-history writer | `risk_score_history` |
| `analytics` (metrics) | `analytics/metrics/` (new) | entity-metric repository (read/write) | `entity_metric_history`, `entity_metrics_current` |
| `monitoring` (alert log) | `adapters/postgres.py` (same file) | alert-history writer | `alert_history` |

Each adapter takes a `ConnectionProvider` injected at the composition root
(`agent/coordinator.py`, `api/dependencies.py`) — the existing
`build_graph_repository`-style pattern. New write methods are exposed via
narrow write protocols defined in the owning module's `adapters/protocols.py`.

The entity-metric repository (Flow 2) lives in a new small
`analytics/metrics/` package keyed only to the two metric tables
(`entity_metric_history`, `entity_metrics_current`). It is kept separate from
`analytics/timeseries/` so `timeseries/` stays a pure read-side consumer and
module boundaries remain narrow.

## 6. Database Schema

All tables are keyed by `knowledge_base_id`. Owned by `database/migrations/`.

| Table | Kind | Purpose |
|-------|------|---------|
| `raw_records` | regular | canonical tabular landing zone |
| `observations` | hypertable (`observed_at`) | scored observations feeding monitoring + timeseries |
| `entity_metric_history` | hypertable (`observed_at`) | graph metrics over time (time-series sink) |
| `entity_metrics_current` | regular | latest metric value per entity (data-table sink) |
| `risk_score_history` | regular | risk assessments over time |
| `alert_history` | regular | analytics-facing alert log |

### 6.1 `raw_records`

| Column | Type | Notes |
|--------|------|-------|
| `knowledge_base_id` | text | PK part |
| `record_type` | text | PK part; matches a `RecordFeedConfig.record_type` |
| `record_id` | text | PK part |
| `payload` | jsonb | the row body; GIN-indexed |
| `source_type` | text | `file_upload` \| `api_push` |
| `source_ref` | text null | filename / endpoint reference |
| `correlation_id` | text | links to the ingest run / pipeline |
| `content_hash` | text | idempotency — `INSERT … ON CONFLICT DO NOTHING` |
| `ingested_at` | timestamptz | default `now()` |

PK `(knowledge_base_id, record_type, record_id)`. GIN index on `payload`.

### 6.2 `observations` (hypertable on `observed_at`)

`knowledge_base_id, entity_id, entity_type, metric_name, score (0..1),
observed_at, rationale, evidence_pack_id null, batch_id, correlation_id`.

`batch_id` corresponds to an ingest correlation/run id so
`ObservationSourceProtocol.load_batch(kb_id, batch_id)` maps to "all
observations written under this run".

### 6.3 `entity_metric_history` (hypertable on `observed_at`)

`knowledge_base_id, entity_id, metric_name, value, observed_at,
correlation_id`. Append-only; backs `TimeSeriesHistorySourceProtocol`.

### 6.4 `entity_metrics_current`

`knowledge_base_id, entity_id, metric_name, value, updated_at`.
PK `(knowledge_base_id, entity_id, metric_name)`. Upserted snapshot for fast
"top-risk entities"-style tabular reads.

### 6.5 `risk_score_history`

`knowledge_base_id, entity_id, request_id, overall_score, risk_level,
factors (jsonb), assessed_at`. Index `(knowledge_base_id, entity_id,
assessed_at desc)` — backs `RiskSignalSourceProtocol.load_historical_score`
and ranked-entry reads.

### 6.6 `alert_history`

`knowledge_base_id, alert_id, entity_id, entity_type, severity, status, title,
reasoning, metric_name, evidence_pack_id null, created_at, updated_at`.
Analytics-facing log; does **not** replace the API's `_alert_store`.

### 6.7 Idempotency

`raw_records` uses `content_hash` + `INSERT … ON CONFLICT DO NOTHING`. Every
history / metric write uses `ON CONFLICT` upserts so the worker's existing
retry/DLQ wrapper can re-run any handler safely.

## 7. Configuration Additions (`config/schema.py`)

- **`DatabaseConfig`** — `backend: Literal["postgres", "in_memory"]`,
  `dsn_env_var: str | None`, `pool_size: int`, `pool_max_overflow: int`,
  `statement_timeout_ms: int`. Follows the `*_env_var` secret pattern. `local`
  (including pytest runs) may use `in_memory`; `dev` / `staging` /
  `production` require `postgres`.
- **`RecordFeedConfig`** — per feed: `name`, `record_type`,
  `source: Literal["file_upload", "api_push"]`, `schema:
  dict[str, PropertyDefinition]` (reuses the existing `PropertyDefinition`
  type), `entity_mapping` (which fields → entity id/type/properties and
  relationships), `observation_mapping` (which fields → metric observations).
- **`RecordsConfig`** — `feeds: list[RecordFeedConfig]`; added to
  `DomainConfig`.
- **`CapabilitiesConfig`** — gains `structured_ingestion: bool = False`.

A new domain's tabular feeds therefore require config changes only — no code,
preserving domain reconfigurability. Both default configs
(`medicare_fraud.yaml`, `food_supply_chain.yaml`) gain example feed
definitions; the dev config (`medicare_fraud_dev.yaml`) gains a
`DatabaseConfig` with `backend: postgres`.

## 8. Data Flows

### Flow 1 — Structured ingest → graph + analytics

```
records/ source (CSV/JSONL/api_push)
  → RecordsService.register_records()      # validate vs RecordFeedConfig.schema
  → RawRecordStore.persist()               # raw_records (canonical)
  → publish RecordsIngestedEvent
  → worker handle_records_ingested:        # single handler (D9)
       1. map rows → Entity/Relationship (config mapper) → GraphService.upsert_task()
       2. derive observations (observation_mapping) → observations table
```

Single handler, graph-upsert-then-observations (D9). Retry/DLQ-wrapped; all
writes idempotent. A graph outage retries the whole handler — acceptable since
both the graph and observation writes are needed downstream anyway.

### Flow 2 — Graph metrics → time-series + data table

```
GraphUpdatedEvent
  → worker handle_graph_updated_for_analytics (extended)
  → GraphService.compute_metrics()
  → entity-metric repository:
       - append rows to entity_metric_history (hypertable)
       - upsert entity_metrics_current (snapshot)
```

### Flow 3 — Risk write-back

```
RiskService.assess()                        # reads PostgresRiskSignalSource
  → publish RiskScoredEvent
  → worker handle_risk_scored_for_graph:
       1. write risk_score_history
       2. GraphService.update_entity_properties()  # risk_score, risk_level, risk_assessed_at
       3. GraphService.upsert_task()               # RiskAssessment node + HAS_ASSESSMENT rel
```

### Flow 4 — Alert write-back

```
MonitoringService.evaluate()                # reads PostgresObservationSource
  → publish AlertsCreatedEvent
  → worker handle_alerts_created_for_graph:
       1. write alert_history
       2. GraphService.update_entity_properties()  # active_alert_count, last_alert_at, last_alert_severity
       3. GraphService.upsert_task()               # Alert node + HAS_ALERT rel
```

### 8.1 New events (`events/types.py` + codec registry)

- `RecordsIngestedEvent` — carries kb_id, correlation_id, record refs.
- (Re-used) `GraphUpdatedEvent`, `RiskScoredEvent`, `AlertsCreatedEvent` —
  already published; new handlers subscribe to them.

New event types are registered in the `events/codec.py` registry.

### 8.2 New / extended worker handlers (`agent/coordinator.py`)

| Handler | Trigger | Action |
|---------|---------|--------|
| `handle_records_ingested` | `RecordsIngestedEvent` | Flow 1 |
| `handle_graph_updated_for_analytics` (extend) | `GraphUpdatedEvent` | Flow 2 (add metric persistence) |
| `handle_risk_scored_for_graph` | `RiskScoredEvent` | Flow 3 |
| `handle_alerts_created_for_graph` | `AlertsCreatedEvent` | Flow 4 |

## 9. Consistency Model

Postgres write commits → event published → graph write happens in the handler.
Cross-DB and eventually consistent; there is no distributed transaction. A
graph-write failure routes to the DLQ and is replayable because every write is
an idempotent upsert. This matches the platform's existing event-driven,
retry/DLQ-wrapped worker model.

## 10. Architectural-Rule Compliance

- **Protocol + adapter for every external system.** Postgres is reached only
  through `ConnectionProvider` and per-module repository adapters; no module
  imports psycopg outside an adapter.
- **Three cross-module paths only.** `records/` talks downstream solely by
  publishing events (agent-coordinator path). Analytics adapters depend on the
  `ConnectionProvider` *protocol*; concrete wiring is injected at the
  composition root. `database/` imports only `config` + `shared`.
- **No hardcoded domain types.** `raw_records` is generic (`record_type` +
  JSONB); feed schemas live in `DomainConfig`. No `Claim` / `Provider` table
  or class is introduced.
- **Domain reconfigurability.** A new domain's feeds, entity mappings, and
  observation mappings are config-only.
- **`DomainConfig` literals.** `DatabaseConfig.backend` adds only `postgres`
  and `in_memory` — both have adapters and factory wiring in this design, so
  the roadmap-adapter rule is satisfied.

## 11. Error Handling

- `database/exceptions.py` defines a `DatabaseError` hierarchy
  (`DatabaseConnectionError`, `MigrationError`, `QueryError`). Adapters
  translate psycopg exceptions; raw driver errors never leak across the module
  boundary.
- API and worker startup fail fast when `DatabaseConfig.backend == "postgres"`
  and the pool cannot connect — matching the existing `CHILI_ENV` strictness.
- `statement_timeout_ms` bounds runaway queries.
- Worker handlers are already retry/DLQ-wrapped; combined with idempotent
  upserts this makes every flow safely replayable.

## 12. Testing Strategy

- **Unit (fast, default suite):** in-memory adapters keep every package's
  pytest suite green at ≥ 85% coverage. New `records/`, `database/` config and
  model code, mappers, and the four worker handlers are unit-tested with
  in-memory adapters.
- **Integration (`@pytest.mark.integration`):** Postgres adapters tested
  against a real Timescale instance (dev-compose service or testcontainers),
  skipped when the optional `[postgres]` extra / a running DB is absent —
  mirroring the Neo4j and Qdrant adapter test pattern.
- **Migration test:** apply all Alembic migrations to a fresh database and
  assert the resulting schema (tables, hypertables, indexes).
- **E2E:** a Playwright/worker end-to-end test ingests a CSV feed and asserts
  the resulting graph entities **and** `observations` rows.
- `pyright --strict` clean for every new module; new modules added to
  `tool.pyright.include` in `pyproject.toml`.

## 13. Packaging & Ops

- New optional dependency group `[postgres]` in `backend/pyproject.toml`
  (`psycopg[binary]` 3.x, `alembic`).
- `docker-compose.dev.yaml`: the `postgres` service image is switched to a
  TimescaleDB image (`timescale/timescaledb:*-pg16`); `DATABASE_URL` is already
  wired into `api` and `worker`.
- A startup / make target runs Alembic migrations against the dev database.
- `infra/` Helm / k8s manifests gain a Timescale/Postgres service definition
  (baseline; production tuning deferred).

## 14. Documentation Updates (on implementation)

- `docs/architecture.md` — add `database/` and `records/` to the module
  decomposition, the container topology, and the data-flow section.
- `backend/README.md` — add the two modules, the `[postgres]` extra, the
  migration command, and the new env vars to the Current State and
  Environment Variables sections.
- New `backend/database/README.md` and `backend/records/README.md`.
- `.github/copilot-instructions.md` — keep consistent with `CLAUDE.md`.

## 15. Future Work (explicitly out of scope)

- Timescale retention / continuous-aggregate / downsampling policies.
- Streaming ingestion sources (Kafka, etc.) for `records/`.
- Typed materialized projections over `raw_records` for high-traffic feeds.
- Backfill tooling to replay `raw_records` into the graph after a mapping
  change.
