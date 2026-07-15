# database backlog

> **Scope:** Postgres + TimescaleDB connection provider, Alembic migrations, schema lifecycle, observability, backup/restore, tenant scoping, TLS.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story database.01: Land the Plan B `workflow_runs` Postgres schema migration

**ID:** database.01
**Status:** planned
**Prerequisites:** [database.03, database.04]
**Unblocks:** [_multitenancy.05, _observability.10, _security.02, _security.06, agent.09, agent.18, llm.08, records.02, records.05, vectorstore.02]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-14-backend-persistence-design.md

> **Scope (2026-06-23 PM decision):** This story owns the `workflow_runs` / `workflow_run_history` / `workflow_run_idempotency` Alembic **schema migration** only — the persistence baseline its dependents rely on. The `PostgresWorkflowRunStore` **adapter** and the `postgres` runtime selector are owned by [agent.18], which depends on this migration. (Resolves the prior agent.18 ⟷ database.01 duplicate.)

**As a** platform operator running the worker against a multi-replica deployment,
**I need** workflow run state, history, and idempotency keys persisted in Postgres,
**so that** the worker survives Redis loss without losing audit-grade workflow lifecycle and so the "Plan B" gap from the persistence design spec is finally closed.

### Current State
- `agent/adapters/runtime.py:18-29` only accepts `in_memory` and `redis` for `CHILI_WORKFLOW_RUN_STORE_BACKEND`; there is no `postgres` branch.
- `RedisWorkflowRunStore` (`agent/adapters/redis_store.py`) encodes the canonical hash layout (one run per key, per-update history list, idempotency-key index) but is the only durable backend.
- The current migration chain through `0007_case_feedback.py` defines Plan-C persistence tables plus cases, policy items, record submissions, conversations, derived signals, and case feedback — no `workflow_runs`, `workflow_run_history`, or `workflow_run_idempotency` table exists.
- `agent/adapters/protocols.py` `WorkflowRunStoreProtocol` exposes `save_run`, `get_run`, `list_runs`, `update_run`, `find_by_correlation_id`, `find_by_idempotency_key`, `record_idempotency` — every method must round-trip through SQL.

### Acceptance Criteria
- [ ] A new Alembic revision after the current head adds `workflow_runs`, `workflow_run_history`, `workflow_run_idempotency` tables keyed by `(knowledge_base_id, run_id)` with composite indexes on `correlation_id`, `idempotency_key`, and `created_at DESC`; raw-SQL only (no ORM).
- [ ] `make migrate` against a fresh dev compose stack applies the revision cleanly and is reversible (`downgrade` drops the three tables).
- [ ] `backend/database/README.md` documents the schema; `docs/architecture.md` §6.4 is updated to remove the "Plan B schema not landed" note.
- [ ] The `PostgresWorkflowRunStore` adapter and the `postgres` runtime selector that consume this schema are delivered by [agent.18] (not this story).

### Verification
- `make migrate` against a fresh dev compose stack succeeds; `\d workflow_runs` shows the three tables and their indexes; `downgrade -1` removes them cleanly.
- `pyright --strict` clean for `backend/database/`.

### Code touch points
- backend/database/migrations/versions/<next>_workflow_runs.py (new)
- backend/agent/adapters/postgres_store.py (new)
- backend/agent/adapters/runtime.py (modify)
- backend/agent/adapters/__init__.py (modify)
- backend/tests/agent/test_postgres_store.py (new)
- backend/database/README.md (modify)
- backend/agent/README.md (modify)
- docs/architecture.md (modify §6.4 row)

---

## Story database.02: Add Postgres knowledge-base metadata adapter

**ID:** database.02
**Status:** planned
**Prerequisites:** [database.03, database.04]
**Unblocks:** [_multitenancy.06, _observability.09, api.02, api.03, api.04, config.06, knowledgebases.01]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-14-backend-persistence-design.md

**As a** platform operator running the API with concurrent analysts,
**I need** knowledge-base, document, and document-version metadata persisted in Postgres,
**so that** KB mutations are durable and concurrent-safe instead of relying on the dev-only single-writer JSON blob adapter.

### Current State
- `backend/knowledgebases/adapters/` ships only `InMemoryKnowledgeBaseRepository` and `ObjectStoreKnowledgeBaseRepository` — no Postgres backend.
- `architecture.md:1369` explicitly flags "Add a production-grade KB metadata adapter/migration path" as an open production gap.
- `api/dependencies.py:740-760` selects the backend from `CHILI_KB_REPOSITORY_BACKEND` with only two valid values (`in_memory`, `object_store`).
- The KB metadata schema (knowledge_bases, documents, document_versions) does not yet exist in any Alembic revision.
- Current database migration head is `0007_case_feedback`; earlier numeric revision names `0002` and `0003` are already used for cases and policy tables.

### Acceptance Criteria
- [ ] A new Alembic revision after the current head adds `knowledge_bases`, `documents`, and `document_versions` tables with appropriate FKs, status/timestamp columns matching `shared/types.py::KnowledgeBase`, and indexes on `(knowledge_base_id, created_at DESC)` for listing.
- [ ] `backend/knowledgebases/adapters/postgres.py` defines `PostgresKnowledgeBaseRepository` implementing the existing `KnowledgeBaseRepository` protocol; reads and writes go through a `ConnectionProvider`; mutations are `INSERT … ON CONFLICT` upserts.
- [ ] `api/dependencies.py:get_knowledge_base_repository` accepts `CHILI_KB_REPOSITORY_BACKEND=postgres`, injects the shared `ConnectionProvider`, and fails fast with a clear error when no DSN is configured.
- [ ] `pytest -m integration backend/tests/knowledgebases/test_postgres_repository.py` covers create / list / get / delete / register_document / delete_document and runs ≥ 85% line coverage on the new adapter.
- [ ] `backend/knowledgebases/README.md`, `backend/database/README.md`, and `docs/architecture.md:1369` are updated to remove the "production gap" note.

### Verification
- `make migrate && pytest -m integration backend/tests/knowledgebases/test_postgres_repository.py --cov=backend.knowledgebases.adapters.postgres` reports ≥ 85% coverage.
- Smoke: `CHILI_KB_REPOSITORY_BACKEND=postgres` start the API, `POST /knowledgebases`, `GET /knowledgebases`, then `SELECT * FROM knowledge_bases` confirms persistence; restart API; `GET /knowledgebases` still returns the row.
- `pyright --strict` clean for `backend/knowledgebases/` and `backend/api/`.

### Code touch points
- backend/database/migrations/versions/<next>_kb_metadata.py (new)
- backend/knowledgebases/adapters/postgres.py (new)
- backend/knowledgebases/adapters/__init__.py (modify)
- backend/api/dependencies.py (modify get_knowledge_base_repository)
- backend/tests/knowledgebases/test_postgres_repository.py (new)
- backend/knowledgebases/README.md (modify)
- backend/database/README.md (modify)
- docs/architecture.md (modify §7 gap note)

---

## Story database.03: Establish zero-downtime / expand-then-contract migration convention

**ID:** database.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** [agent.18, analytics.17, analytics.23, database.01, database.02, database.08, database.09, database.11, database.13]
**Estimated size:** M

**As a** developer adding any future schema change,
**I need** a documented and lint-enforced convention for backward-compatible expand-then-contract migrations,
**so that** schema changes never break a deployed pod mid-rollout and every later migration starts from the same playbook.

### Current State
- Only one revision exists (`0001_persistence_baseline`); there is no template, no "expand-then-contract" pair, no `pre_deploy` vs `post_deploy` split documented anywhere.
- `backend/database/README.md` has no migration-authoring section.
- Nothing today rejects a revision that mixes `DROP COLUMN`, `ALTER COLUMN TYPE`, or `RENAME` with new code references in a single commit.

### Acceptance Criteria
- [ ] `backend/database/README.md` gains a "Migration Conventions" section: additive-first rule, expand-then-contract pattern, `pre_deploy_` / `post_deploy_` filename prefixes, advisory-lock guidance, and a worked example of renaming a column without a write outage.
- [ ] A template revision (`backend/database/migrations/versions/_template_expand_contract.py.example`, ignored by Alembic) documents the two-revision pattern with comments.
- [ ] `scripts/check_migration_conventions.py` parses every file under `backend/database/migrations/versions/` and refuses (exit 1) any revision that contains `DROP COLUMN`, `ALTER COLUMN ... TYPE`, or `ALTER TABLE ... RENAME` unless the filename carries a `post_deploy_` prefix.
- [ ] `tests/scripts/test_check_migration_conventions.py` covers passing and failing fixtures, ≥ 85% line coverage.
- [ ] CLAUDE.md and `.github/copilot-instructions.md` reference the convention under "Common Commands → Backend" so future agents follow it.

### Verification
- `python scripts/check_migration_conventions.py` exits 0 on `main`; introducing a fixture revision with `DROP COLUMN provider` exits 1 with a clear message.
- `pytest tests/scripts/test_check_migration_conventions.py --cov` reports ≥ 85% coverage.

### Code touch points
- backend/database/README.md (modify)
- backend/database/migrations/versions/_template_expand_contract.py.example (new)
- scripts/check_migration_conventions.py (new)
- tests/scripts/test_check_migration_conventions.py (new)
- CLAUDE.md (modify)
- .github/copilot-instructions.md (modify)

---

## Story database.04: Add CI migration drift / replay gate

**ID:** database.04
**Status:** done
**Prerequisites:** []
**Unblocks:** [_cicd.12, analytics.20, database.01, database.02, database.08, database.09, ingestion.05, ingestion.18]
**Estimated size:** M
**Done:** 2026-07-14 · BL-042 (Sprint 2026-26) · `feat/sprint-2026-26-ingestion-visibility`

**As a** developer merging schema-touching PRs,
**I need** CI to prove that `alembic upgrade head` applies cleanly against a fresh database and that no schema drift exists between the migration head and the live schema,
**so that** a missing or out-of-order revision fails the PR rather than the production deploy.

### Current State (shipped)
- `scripts/ci_migration_check.sh` owns the whole gate: compose `postgres` service up, scratch database `chili_migration_check` (never the dev `chili` DB), `upgrade head` → `downgrade base` → `upgrade head`, normalized `pg_dump --schema-only` from inside the container, diff vs the committed `backend/database/migrations/snapshots/head.sql` (check mode) or snapshot rewrite (`--update-snapshot`).
- `make migrate-check` / `make migrate-snapshot` give local parity; the `migrations` CI job (`ci.yml`) runs the identical script.
- Snapshot-diff was chosen over `alembic check` (content-based, no revision IDs in the snapshot); refresh rule documented in `backend/database/README.md`.
- The first real CI run failed because `snapshots/head.sql` had been planned as a committed artifact but never generated — caught by the 2026-07-14 verification pass, generated via `make migrate-snapshot`, committed, and the `migrations` job now reports green.

### Acceptance Criteria
- [x] `scripts/ci_migration_check.sh` starts a fresh TimescaleDB container, runs `alembic upgrade head`, runs `alembic downgrade base`, runs `alembic upgrade head` again, then exits 0 — proves both directions and idempotent replay.
- [x] The script also runs `alembic check` (or a schema-snapshot diff using `pg_dump --schema-only` against a committed `backend/database/migrations/snapshots/head.sql`) and fails on drift between `head.sql` and the live schema.
- [x] A `make migrate-check` Makefile target invokes the same script for local parity with CI.
- [x] `backend/database/migrations/snapshots/head.sql` is committed and updated whenever a new revision lands; documented in `backend/database/README.md`.
- [x] `_cicd.12`'s GitHub Actions job invokes the script; this story closes when the gate reports green on `main`. (Green on the sprint branch 2026-07-14; the job runs on `prod` pushes and PRs, so it re-proves at merge.)

### Verification
- `make migrate-check` exits 0 on a clean checkout.
- Mutating `0001_persistence_baseline.py` (e.g., dropping a column) without updating `snapshots/head.sql` causes the script to exit non-zero with a diff.
- CI run on `_cicd.12`'s PR shows the drift gate as a required check.

### Code touch points
- scripts/ci_migration_check.sh (new)
- backend/database/migrations/snapshots/head.sql (new)
- backend/database/README.md (modify)
- Makefile (modify, add migrate-check target)
- backend/database/migrations/env.py (modify to populate target_metadata for alembic check, if chosen path)

---

## Story database.05: Production-grade connection pool tuning

**ID:** database.05
**Status:** planned
**Prerequisites:** []
**Unblocks:** [analytics.07, analytics.11, api.19, database.06, database.10, storage.10]
**Estimated size:** M

**As a** worker / API operator under production concurrency,
**I need** the psycopg pool tuned with realistic timeouts, keepalives, an `application_name`, and per-environment defaults,
**so that** stuck queries, dead TCP connections, and noisy-neighbor pods do not exhaust the pool or leave orphaned sessions.

### Current State
- `config/schema.py:159-166` exposes only `pool_size=10`, `pool_max_overflow=5`, `statement_timeout_ms=30000` — no connect timeout, no acquire timeout, no keepalives, no `application_name`.
- `engine._configure` (`backend/database/engine.py:60-69`) sets `statement_timeout` only.
- `config/defaults/medicare_fraud.yaml` and `medicare_fraud_dev.yaml` don't override pool sizing per environment.
- `_normalize_dsn` (`engine.py:36-39`) strips the SQLAlchemy prefix but does not inject `application_name`.

### Acceptance Criteria
- [ ] `DatabaseConfig` (`config/schema.py:159-166`) gains `connect_timeout_seconds: int = 5`, `pool_acquire_timeout_seconds: float = 10.0`, `keepalives_idle_seconds: int = 30`, `keepalives_interval_seconds: int = 10`, `keepalives_count: int = 3`, `application_name: str = "chili"` — all with Pydantic `Field` constraints.
- [ ] `engine.create_connection_pool` applies the new settings via the psycopg `kwargs={"connect_timeout": ..., "keepalives": 1, ...}` and `timeout=` argument to `ConnectionPool.connection()`.
- [ ] `_normalize_dsn` (or a sibling helper) appends `?application_name=chili-api` / `chili-worker` based on a `service_name` argument so `pg_stat_activity` distinguishes the two callers.
- [ ] `config/defaults/medicare_fraud.yaml` ships staging/production defaults (pool_size=20, max_overflow=10) and `medicare_fraud_dev.yaml` keeps the smaller dev defaults.
- [ ] `pytest backend/tests/database/test_engine.py` exercises every new field at ≥ 85% coverage and `pyright --strict` is clean.

### Verification
- `pytest backend/tests/database/test_engine.py --cov=backend.database.engine` ≥ 85%.
- `SELECT application_name, count(*) FROM pg_stat_activity GROUP BY 1;` against a running dev stack shows `chili-api` and `chili-worker` rows distinctly.
- Killing the database mid-query causes the pool to refuse new checkouts after `pool_acquire_timeout_seconds` rather than hanging the request.

### Code touch points
- backend/config/schema.py (modify DatabaseConfig)
- backend/database/engine.py (modify create_connection_pool + _normalize_dsn / new helper)
- backend/database/runtime.py (modify create_connection_provider to thread service_name)
- backend/api/dependencies.py (modify get_connection_provider)
- backend/agent/coordinator.py (modify provider construction)
- backend/config/defaults/medicare_fraud.yaml (modify)
- backend/config/defaults/medicare_fraud_dev.yaml (modify)
- backend/tests/database/test_engine.py (new or extend)
- backend/database/README.md (modify)

---

## Story database.06: Read-replica routing through ConnectionProvider

**ID:** database.06
**Status:** planned
**Prerequisites:** [database.05, _infra.06]
**Unblocks:** [monitoring.11]
**Estimated size:** L

**As a** developer of an analytics read endpoint,
**I need** the `ConnectionProvider` to optionally hand out a read-only connection backed by a replica pool,
**so that** heavy analytics reads stop competing with worker writes on the primary.

### Current State
- `protocols.py:47-53` exposes only `connection()` with no read-only mode.
- `engine.py:93-96` returns the writer connection unconditionally.
- `monitoring/adapters/postgres.py`, `analytics/timeseries/adapters/postgres.py`, `analytics/risk/adapters/postgres.py`, `analytics/metrics/adapters/postgres.py` all share the single writer pool.
- No `READ_REPLICA_URL` plumbing exists in `DatabaseConfig` or `runtime.py`.
- `_infra.06` owns the actual managed-replica provisioning; this story owns the application-side selector.

### Acceptance Criteria
- [ ] `ConnectionProvider.connection(read_only: bool = False)` lands in `database/protocols.py`; the writer is the default to preserve callers that don't opt in.
- [ ] `DatabaseConfig` gains `read_replica_dsn_env_var: str | None = None`; when set, `runtime.create_connection_provider` builds a second psycopg pool sized via `read_pool_size`/`read_pool_max_overflow` defaults.
- [ ] `PsycopgConnectionProvider` routes `connection(read_only=True)` to the reader pool when available, falls back to the writer pool with a single `logger.warning` once per process when not.
- [ ] All four read-side analytics adapters (`monitoring`, `analytics/timeseries`, `analytics/risk`, `analytics/metrics`) call `connection(read_only=True)` on pure-read paths; writes continue to use the default.
- [ ] `pytest backend/tests/database/test_runtime.py` covers reader-present, reader-absent fallback, and adapter call-site selection at ≥ 85% coverage on `engine.py` and `runtime.py`.

### Verification
- `READ_REPLICA_URL=…` plus `DATABASE_URL=…` starts the API; `SELECT pg_is_in_recovery()` from inside a `connection(read_only=True)` returns `t` against the replica.
- Removing `READ_REPLICA_URL` falls back to the writer pool without raising.
- `pyright --strict` clean for `backend/database/`, `backend/monitoring/adapters/`, `backend/analytics/`.

### Code touch points
- backend/database/protocols.py (modify)
- backend/database/engine.py (modify)
- backend/database/runtime.py (modify)
- backend/config/schema.py (modify DatabaseConfig)
- backend/monitoring/adapters/postgres.py (modify read paths)
- backend/analytics/timeseries/adapters/postgres.py (modify)
- backend/analytics/risk/adapters/postgres.py (modify)
- backend/analytics/metrics/adapters/postgres.py (modify)
- backend/tests/database/test_runtime.py (extend)
- backend/database/README.md (modify)

---

## Story database.07: Enforce TLS to the database from API and worker

**ID:** database.07
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_security.05, agent.06, agent.18, monitoring.04]
**Estimated size:** M

**As a** security reviewer signing off on a staging/production deploy,
**I need** all Postgres connections to use `sslmode=verify-full` with a configured CA bundle and an explicit refusal to start when `sslmode=disable` is resolved in non-`local` environments,
**so that** database credentials and PHI/PII rows never cross an unencrypted link.

### Current State
- `engine._normalize_dsn` (`engine.py:36-39`) only strips the SQLAlchemy prefix; nothing inspects or enforces `sslmode`.
- `docker-compose.dev.yaml` ships `postgresql://chili:chili@postgres:5432/chili` with no SSL parameter.
- `DatabaseConfig` (`config/schema.py:159-166`) has no `sslmode` or `sslrootcert` field.
- `_security.05` owns the cross-cutting "TLS posture" story; this story owns the database-side knob and the startup refusal.

### Acceptance Criteria
- [ ] `DatabaseConfig` adds `sslmode: Literal["disable", "allow", "prefer", "require", "verify-ca", "verify-full"] = "prefer"` and `sslrootcert_path: str | None = None`; new Pydantic validator forbids `sslmode in {"disable","allow","prefer"}` when `os.environ["CHILI_ENV"]` is `staging` or `production`.
- [ ] `engine.create_connection_pool` injects `sslmode=` and (when set) `sslrootcert=` into the psycopg kwargs / DSN; failure to load the CA file raises `DatabaseConnectionError` with a clear message.
- [ ] `config/defaults/medicare_fraud.yaml` ships `sslmode: verify-full`; `medicare_fraud_dev.yaml` keeps `sslmode: prefer` (so dev stays usable but documented as non-production).
- [ ] `pytest backend/tests/database/test_engine.py` covers each sslmode branch and the env-gated refusal; coverage ≥ 85% per file.
- [ ] `backend/database/README.md` documents the matrix, the CA-bundle path convention, and how to test locally with `openssl s_client`.

### Verification
- `CHILI_ENV=production DATABASE_URL=postgresql://…?sslmode=disable uvicorn api.app:create_app --factory` exits non-zero with a typed error.
- `CHILI_ENV=production DATABASE_URL=postgresql://…?sslmode=verify-full` starts cleanly against a TLS-terminated Postgres; `SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()` returns `t`.
- `pyright --strict` clean.

### Code touch points
- backend/config/schema.py (modify DatabaseConfig)
- backend/database/engine.py (modify)
- backend/database/runtime.py (modify if needed)
- backend/config/defaults/medicare_fraud.yaml (modify)
- backend/config/defaults/medicare_fraud_dev.yaml (modify)
- backend/tests/database/test_engine.py (extend)
- backend/database/README.md (modify)
- docs/security_checklist.md (modify, cross-link to _security.05)

---

## Story database.08: Add tenant_id columns and row-level-security to every Plan C table

**ID:** database.08
**Status:** planned
**Prerequisites:** [database.03, database.04]
**Unblocks:** [_multitenancy.05, knowledgebases.08]
**Estimated size:** L
**Spec:** docs/superpowers/specs/2026-05-14-backend-persistence-design.md

**As a** platform operator running chiliAI as a multi-tenant SaaS,
**I need** every Plan C table to carry a `tenant_id` column, composite PKs/indexes including it, and an RLS policy keyed off a `chili.tenant_id` GUC,
**so that** an adapter-layer bug or a missing `WHERE` clause cannot leak rows across tenants.

### Current State
- Every table in `0001_persistence_baseline` keys on `knowledge_base_id` only (lines 31, 54, 79, 98, 113, 131); no `tenant_id` exists anywhere.
- No RLS policy is enabled on any table; `ALTER TABLE … ENABLE ROW LEVEL SECURITY` appears nowhere.
- No adapter today sets `SET LOCAL chili.tenant_id` per connection checkout.
- `_multitenancy.05` owns the column-addition migration's overall shape across the platform; this story is the database-side migration + adapter-side GUC-injection wiring for the Plan C tables specifically.

### Acceptance Criteria
- [ ] Alembic revision `0004_tenant_scoping_planc.py` adds `tenant_id text NOT NULL` to `raw_records`, `observations`, `entity_metric_history`, `entity_metrics_current`, `risk_score_history`, `alert_history`; backfills existing rows with the value derived from `knowledge_base_id` (or `'default'` if KB→tenant mapping is unset); extends every primary key and composite index to lead with `tenant_id`.
- [ ] The same revision runs `ALTER TABLE … ENABLE ROW LEVEL SECURITY` and `CREATE POLICY p_tenant ON … USING (tenant_id = current_setting('chili.tenant_id', true))` on each of the six tables.
- [ ] `PsycopgConnectionProvider.connection()` accepts an optional `tenant_id` argument that emits `SET LOCAL chili.tenant_id = :tenant` on first cursor use within the context; raises if missing in non-`local` environments.
- [ ] All six Plan-C adapters (`monitoring/adapters/postgres.py`, `analytics/timeseries/adapters/postgres.py`, `analytics/risk/adapters/postgres.py`, `analytics/metrics/adapters/postgres.py`, `records/adapters/postgres.py`, and the alert-history writer) call `connection(tenant_id=…)` with the tenant resolved from request / event context.
- [ ] Two-tenant integration test: writing rows under `tenant_id=A`, then `SET LOCAL chili.tenant_id = 'B'`, then `SELECT` returns zero A-rows from each table. Coverage ≥ 85% on the migration and adapter changes.

### Verification
- `make migrate` against the dev stack succeeds; `\d+ observations` shows `tenant_id` in the PK and an RLS policy enabled.
- `pytest -m integration backend/tests/database/test_rls_planc.py` proves no cross-tenant leak across all six tables.
- `pyright --strict` clean for every touched adapter.

### Code touch points
- backend/database/migrations/versions/0004_tenant_scoping_planc.py (new)
- backend/database/protocols.py (modify connection signature)
- backend/database/engine.py (modify PsycopgConnectionProvider.connection)
- backend/monitoring/adapters/postgres.py (modify)
- backend/analytics/timeseries/adapters/postgres.py (modify)
- backend/analytics/risk/adapters/postgres.py (modify)
- backend/analytics/metrics/adapters/postgres.py (modify)
- backend/records/adapters/postgres.py (modify)
- backend/tests/database/test_rls_planc.py (new)
- backend/database/README.md (modify)

---

## Story database.09: TimescaleDB retention, compression, and continuous-aggregate policies

**ID:** database.09
**Status:** planned
**Prerequisites:** [database.03, database.04]
**Unblocks:** [database.12]
**Estimated size:** M
**Spec:** docs/superpowers/specs/2026-05-14-backend-persistence-design.md

**As a** platform operator,
**I need** the two hypertables (`observations`, `entity_metric_history`) to have retention, compression, and a continuous-aggregate policy,
**so that** disk usage stays bounded and the daily entity-metric rollup is computed once instead of on every read.

### Current State
- `0001_persistence_baseline` calls `create_hypertable` on `observations` and `entity_metric_history` but sets no retention or compression — explicitly deferred by spec §15.
- There is no continuous aggregate feeding `entity_metrics_current` today; the snapshot table is upserted in-band by the worker on every `GraphUpdatedEvent`.
- `dev-compose` ships `timescale/timescaledb:latest-pg16` which supports Apache-licensed retention / compression / continuous aggregates.

### Acceptance Criteria
- [ ] Alembic revision `0005_timescale_policies.py` calls `add_retention_policy('observations', INTERVAL '90 days')` and `add_retention_policy('entity_metric_history', INTERVAL '365 days')`.
- [ ] The same revision calls `ALTER TABLE … SET (timescaledb.compress, timescaledb.compress_segmentby = 'knowledge_base_id, entity_id')` on both hypertables and `add_compression_policy(…, INTERVAL '7 days')`.
- [ ] The revision creates a `daily_entity_metric_summary` continuous aggregate that buckets `entity_metric_history` to one day per `(knowledge_base_id, entity_id, metric_name)` and registers `add_continuous_aggregate_policy(…, start_offset => '7 days', end_offset => '1 hour', schedule_interval => '1 hour')`.
- [ ] `backend/database/README.md` documents the policy choices, how to override per-environment by additional revisions, and how to verify with `SELECT * FROM timescaledb_information.jobs`.
- [ ] `pytest -m integration backend/tests/database/test_timescale_policies.py` asserts every policy is registered against a fresh migrated DB.

### Verification
- `make migrate` against the dev stack; `SELECT job_id, application_name FROM timescaledb_information.jobs` shows the retention, compression, and continuous-aggregate jobs.
- `pytest -m integration backend/tests/database/test_timescale_policies.py` green.

### Code touch points
- backend/database/migrations/versions/0005_timescale_policies.py (new)
- backend/database/README.md (modify)
- backend/tests/database/test_timescale_policies.py (new)
- docs/architecture.md (modify §5.2 row to drop "deferred" qualifier)

---

## Story database.10: Query observability — pg_stat_statements, slow-query log, pool metrics, DB-span tracing

**ID:** database.10
**Status:** planned
**Prerequisites:** [database.05, _observability.04]
**Unblocks:** []
**Estimated size:** L

**As an** operator triaging a slow query or pool saturation,
**I need** `pg_stat_statements` enabled, slow queries logged, pool gauges exported to Prometheus, and an OpenTelemetry span around every `provider.connection()` checkout,
**so that** every slow path has a measurable, traceable, and queryable signal instead of disappearing into the pool.

### Current State
- Nothing in `database/` enables `pg_stat_statements` or sets `log_min_duration_statement`.
- `PsycopgConnectionProvider.connection` (`engine.py:93-96`) yields the pooled connection without any metric or span emission.
- No Prometheus gauges exist for psycopg-pool checkout wait, idle, or in-use counts.
- `_observability.04` owns the platform-wide metric catalog; this story owns the database-side emission points and `pg_stat_statements` provisioning.

### Acceptance Criteria
- [ ] `docker-compose.dev.yaml` Postgres command adds `-c shared_preload_libraries=timescaledb,pg_stat_statements -c pg_stat_statements.track=all -c log_min_duration_statement=500`; an Alembic revision `0006_pg_stat_statements.py` runs `CREATE EXTENSION IF NOT EXISTS pg_stat_statements`.
- [ ] `PsycopgConnectionProvider.connection()` wraps each checkout in `tracer.start_as_current_span("db.connection.checkout", attributes={"db.system": "postgresql", "db.application_name": …, "db.read_only": …})` using the existing `shared/tracing.py` setup.
- [ ] Prometheus gauges `db_pool_checkouts_in_use`, `db_pool_checkouts_idle`, `db_pool_acquire_wait_seconds` (histogram) land in `backend/database/metrics.py` and are scraped by the existing `/metrics` endpoint.
- [ ] `backend/database/README.md` documents how to query `pg_stat_statements` for the top-N slow queries and how to read the new metrics in Grafana.
- [ ] `pytest backend/tests/database/test_metrics.py` and a slow-query integration test ≥ 85% coverage on `metrics.py` and the new instrumented code paths.

### Verification
- `make dev`; `psql -c "SELECT query, calls FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 5"` returns rows.
- `curl localhost:8000/metrics | grep db_pool_` shows the three series.
- Jaeger / OTLP receiver shows `db.connection.checkout` spans nested under HTTP request spans.
- Killing a request mid-pool-wait shows the histogram tick.

### Code touch points
- backend/database/engine.py (modify, add span + metric emission)
- backend/database/metrics.py (new)
- backend/database/migrations/versions/0006_pg_stat_statements.py (new)
- docker-compose.dev.yaml (modify postgres command)
- backend/tests/database/test_metrics.py (new)
- backend/database/README.md (modify)

---

## Story database.11: Per-table column comments and auto-generated schema docs

**ID:** database.11
**Status:** planned
**Prerequisites:** [database.03]
**Unblocks:** []
**Estimated size:** M

**As a** developer onboarding to the persistence schema,
**I need** every table and column to carry a `COMMENT` and an auto-generated `docs/database/schema.md` (with a Mermaid ER diagram),
**so that** the schema is self-documenting and the docs cannot drift from the live DDL.

### Current State
- `0001_persistence_baseline` has zero `COMMENT ON COLUMN` or `COMMENT ON TABLE` statements.
- No ER diagram exists under `docs/` (Mermaid or otherwise).
- The only "schema reference" today is reading the migration file plus the design spec narrative.

### Acceptance Criteria
- [ ] Alembic revision `0007_schema_comments.py` adds `COMMENT ON TABLE` and `COMMENT ON COLUMN` for every column of the six Plan-C tables and any tables added by `database.01` / `database.02` that have landed.
- [ ] `scripts/dump_schema_docs.py` (stdlib + psycopg only) connects to a freshly-migrated database, queries `information_schema.tables` and `pg_description`, and emits `docs/database/schema.md` containing one section per table with column-comment-derived prose, plus a Mermaid ER diagram block.
- [ ] `make schema-docs` runs the script against the dev compose Postgres and writes the file.
- [ ] `tests/scripts/test_dump_schema_docs.py` covers the script against a minimal fixture schema at ≥ 85% coverage.
- [ ] `docs/database/schema.md` is committed and referenced from `backend/database/README.md`, `docs/architecture.md` §5.2, and the root `README.md` Documentation table.

### Verification
- `make schema-docs` produces a non-empty, valid Markdown file; rendered Mermaid block parses in the GitHub UI.
- `pytest tests/scripts/test_dump_schema_docs.py --cov` ≥ 85%.
- A reviewer can read `docs/database/schema.md` end-to-end and answer "what is `risk_score_history.factors`?" without opening the migration file.

### Code touch points
- backend/database/migrations/versions/0007_schema_comments.py (new)
- scripts/dump_schema_docs.py (new)
- tests/scripts/test_dump_schema_docs.py (new)
- docs/database/schema.md (new, generated)
- Makefile (modify, add schema-docs target)
- backend/database/README.md (modify)
- docs/architecture.md (modify §5.2 row)
- README.md (modify Documentation table)

---

## Story database.12: Backup, restore, and PITR runbook for the Plan C schema

**ID:** database.12
**Status:** planned
**Prerequisites:** [database.09, _infra.13]
**Unblocks:** []
**Estimated size:** M

**As an** operator responsible for data durability,
**I need** a documented `pg_dump` / `pg_restore` / PITR matrix for the Plan C schema and a quarterly restore-drill checklist that I can rehearse against the dev stack,
**so that** "we have backups" is provable rather than assumed.

### Current State
- `infra/` has no Postgres backup CronJob today — that platform-side work is owned by `_infra.13`.
- There is no documented per-table dump / exclude matrix, no RPO / RTO target, and no restore drill anywhere in `docs/`.
- `Makefile` exposes no `restore-drill` target.

### Acceptance Criteria
- [ ] `docs/database/backup_restore.md` ships and contains: per-table dump strategy (which to exclude for size, what hypertable chunks to dump partially), `pg_dump` / `pg_restore` invocations validated against the dev stack, the chosen RPO (e.g. ≤ 15 min via continuous WAL archiving) and RTO (e.g. ≤ 1 h), the quarterly restore-drill checklist, and a step-by-step PITR walkthrough.
- [ ] `make restore-drill` runs an end-to-end drill against the dev compose stack: takes a `pg_basebackup`, generates synthetic writes, replays WAL up to a target LSN, asserts row counts match expected.
- [ ] `scripts/restore_drill.sh` is invoked by the Make target and is idempotent; it leaves the dev stack in the pre-drill state.
- [ ] The runbook is cross-linked from `backend/database/README.md`, `docs/architecture.md` §5.2, and the `_infra.13` story acceptance criteria.
- [ ] First quarterly drill date is committed in the runbook (next quarter from merge date) with a follow-up tracking issue.

### Verification
- `make restore-drill` exits 0 on a clean dev stack and writes a `docs/database/restore_drill_log.md` entry with timestamp + PASS.
- Reading `docs/database/backup_restore.md` start-to-finish, an SRE who has not touched chiliAI before can perform a restore.

### Code touch points
- docs/database/backup_restore.md (new)
- scripts/restore_drill.sh (new)
- Makefile (modify, add restore-drill target)
- backend/database/README.md (modify)
- docs/architecture.md (modify §5.2)

---

## Story database.13: Schema-evolution safety net — online index builds and idempotency-aware backfills

**ID:** database.13
**Status:** planned
**Prerequisites:** [database.03]
**Unblocks:** []
**Estimated size:** M

**As a** developer adding a new index or backfilling a new column on a populated production hypertable,
**I need** a documented pattern for `CREATE INDEX CONCURRENTLY`, batched `ON CONFLICT` backfills, and progress tracking,
**so that** schema evolution never locks writers and a long-running backfill is restartable on crash without double-writing.

### Current State
- Nothing in `backend/database/migrations/` uses `CREATE INDEX CONCURRENTLY`; revisions run inside Alembic's default transaction.
- The persistence-design spec assumes "every history / metric write uses `ON CONFLICT` upserts" (§6.7) but offers no template for adding a new metric column or backfilling rows without locking writers.
- No `scripts/online_backfill.py` helper exists; no progress table; no resumable / restartable pattern.

### Acceptance Criteria
- [ ] `backend/database/migrations/_template_online_backfill.py.example` documents the pattern: a migration that creates the new column nullable with default null, an out-of-band backfill job that batches by primary-key range with `ON CONFLICT DO UPDATE`, and a follow-up `post_deploy_` migration that adds the `NOT NULL` constraint once the backfill is verified.
- [ ] `scripts/online_backfill.py` ships a reusable runner: accepts `--table`, `--key-column`, `--batch-size`, `--start-key`, `--end-key`, a callable `transform` import path, and writes progress to a new `backfill_progress` table created by an Alembic revision `0008_backfill_progress.py`.
- [ ] `CREATE INDEX CONCURRENTLY` is supported by adding a `transactional_ddl = False` opt-in helper used by index-only revisions; documented in `backend/database/README.md`.
- [ ] `tests/scripts/test_online_backfill.py` covers normal, resume-from-crash, and idempotent-replay paths at ≥ 85% coverage.
- [ ] `backend/database/README.md` "Migration Conventions" section is extended with the online-build / backfill pattern, cross-linked from `database.03`'s convention doc.

### Verification
- `python scripts/online_backfill.py --table observations --key-column observed_at --batch-size 1000 --transform tests.fixtures.backfill_double_score:transform --start-key '2026-01-01' --end-key '2026-02-01'` runs to completion against the dev stack and records rows in `backfill_progress`.
- Killing it mid-run and re-invoking resumes from the recorded checkpoint with no double writes.
- `pytest tests/scripts/test_online_backfill.py --cov` ≥ 85%.

### Code touch points
- backend/database/migrations/_template_online_backfill.py.example (new)
- backend/database/migrations/versions/0008_backfill_progress.py (new)
- scripts/online_backfill.py (new)
- tests/scripts/test_online_backfill.py (new)
- backend/database/README.md (modify)
