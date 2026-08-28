# database — Persistence Infrastructure

Postgres + TimescaleDB connection management and schema migrations. This is a
dependency-light infrastructure module (analogous to `events/`): it owns the
connection pool, the `ConnectionProvider` protocol, and every Alembic
migration. It contains no domain logic and no business logic.

## Layout

- `protocols.py` — `ConnectionProvider`, `DatabaseConnection`, `DatabaseCursor`.
  Consumers depend on these protocols, never on psycopg directly.
- `engine.py` — psycopg 3 connection-pool-backed provider (psycopg imported
  lazily, so the module imports cleanly without the `[postgres]` extra).
- `runtime.py` — `create_connection_provider(config)`: returns a provider for
  the `postgres` backend, or `None` for `in_memory` (callers fall back to
  in-memory adapters).
- `health.py` — `check_database_health(provider)` readiness probe.
- `migrations/` — Alembic environment and versioned raw-SQL migrations. Owns
  the whole schema.

## Schema

Core tables (see `docs/architecture.md` and the design spec for details):
`raw_records`, `observations` (hypertable), `entity_metric_history`
(hypertable), `entity_metrics_current`, `risk_score_history`, `alert_history`
(0001 baseline). Later migrations add `cases` (0002, BL-010),
`policy_items` (0003, BL-011), `record_submissions` (0004 —
submission-level records dedup, BL-015), `conversations` (0005 — durable RAG
chat persistence, BL-012), and `entity_derived_signals` (0006 — peer-group
z-score risk signals). Migration 0007 adds `cases.feedback_history` for
analyst feedback history. Migration 0008 adds `scorecard_runs` (generated
scorecard persistence). Migration 0009 adds
`source_document_status` (durable per-document ingestion status projection,
BL-041). Migration 0010 adds `event_dlq` (durable, replayable event
dead-letter records, BL-023 — see `backend/events/README.md` and
`docs/runbooks/event-replay.md`). Migration 0011 adds `timeseries_anomalies`
(persisted self-history anomaly points, PK `(knowledge_base_id, entity_id,
metric_name, observed_at)`, BL-047 — see
`backend/analytics/README.md` § Timeseries series-source contract). Migration
0012 adds `alert_history` read-model columns `entity_label text NOT NULL
DEFAULT ''`, `confidence double precision NOT NULL DEFAULT 0`, and `tags
jsonb NOT NULL DEFAULT '[]'::jsonb` (alerts.36 — `GET /alerts` has been
served from `alert_history` since this branch, replacing the retired
projection blob `api/_alert_store.py`, not seeded `ApiState`). Migration 0013
adds `risk_projections` for persisted SAFE-CMS-003 risk read models.

The SAFE-CMS surge added ten more (2026-08-02 → 08-05): `0014` alert triage
operations, `0015` alert generation metadata, `0016` `audit_log`, `0017`
`explanation_reviews`, `0018` `identity_links`, `0019` `fraud_playbook_snapshots`
(+ `cases.playbook_ref`), `0020` playbook-snapshot KB scoping, `0021`
`workflow_definition_snapshots`, `0022` `governance_eval_runs`, `0023`
`governance_eval_runs.dataset_source_refs`. `0024` adds `score_runs` and
`score_batches`, making score-all runs durable across a restart. `0025` adds
`connectors` + `connector_sync_runs`, `0026` a stale-sync index, `0027`
`score_runs.skipped_entities`, `0028` re-points
`ix_entity_derived_signals_latest` at `interval_start DESC, computed_at DESC`
so the risk-scoring freshness lookup stays index-backed, and `0029` adds a
unique index on `alert_history (alert_id)` so the unscoped alert detail read
and triage actions (`_ALERT_GET_SQL`, `_ALERT_ACK_SQL` in
`monitoring/adapters/postgres.py`, which match on `alert_id` alone) stop
sequentially scanning the table — every other index on it leads with
`knowledge_base_id`.

**Head is `0029_alert_history_alert_id_ix` — 27 tables.** Derive both rather than
trusting this line: `ls database/migrations/versions/` for the head, and
`grep -c 'CREATE TABLE' database/migrations/snapshots/head.sql` for the table
count. This sentence previously read "Head is `0013` — 16 tables total" for ten
revisions after it stopped being true, which is exactly how a new migration gets
authored as `0014_*` on top of an existing one.

## Commands

```bash
uv pip install -e ".[dev,postgres]"  # install the optional extra
alembic upgrade head                 # apply migrations (needs DATABASE_URL)
alembic downgrade base               # drop the schema
pytest tests/database -m "not integration"   # fast unit tests
pytest tests/database -m integration          # needs a running TimescaleDB
```

## Migration drift / replay gate (database.04 / BL-042)

`scripts/ci_migration_check.sh` (repo root) gates every schema-touching PR
(CI job **Migrations (replay + snapshot drift)**; local parity via
`make migrate-check`). Each run:

1. brings up only the compose `postgres` service and force-recreates a
   **scratch** database `chili_migration_check` — the dev `chili` database is
   never touched, and `DATABASE_URL` is scoped per command, never exported;
2. replays the full history on the fresh database: `alembic upgrade head` →
   `alembic downgrade base` (failing if any `public` table is left behind —
   every migration must implement a complete `downgrade()`) →
   `alembic upgrade head`;
3. dumps the resulting schema with in-container `pg_dump --schema-only`
   (normalized: version-comment headers, psql `\restrict` tokens, and the
   `SET`/`set_config` preamble stripped; TimescaleDB hypertable registrations
   appended as a deterministic footer) and diffs it against the committed
   snapshot `backend/database/migrations/snapshots/head.sql`, failing loudly
   with a unified diff on drift.

```bash
make migrate-check     # local parity with the CI job (exit 1 + diff on drift)
make migrate-snapshot  # regenerate snapshots/head.sql (idempotent, re-runnable)
```

**Every PR that adds or edits a migration must run `make migrate-snapshot`
and commit the refreshed `snapshots/head.sql`**, otherwise the CI gate fails
with a diff — that failure is the gate working as designed. Never regenerate
the snapshot just to silence a drift you did not intend. The snapshot is
content-based (`alembic_version` is excluded, so no revision IDs appear in
it); renumbering revision files does not invalidate it.

**Status:** the script, Makefile targets, CI job, and committed
`snapshots/head.sql` are all live as of migration `0009` (BL-042, Sprint
2026-26) and re-verified through `0012` (alerts.36) — every migration added
since has run `make migrate-snapshot` and committed the refreshed snapshot
(for `0012` in a follow-up commit, since the sandbox that authored the
migration had no Docker access for the scratch-database replay), and `make
migrate-check` reports clean replay against the live schema.

## Configuration

`DatabaseConfig` (in the domain config YAML) selects the backend:

| Field | Default | Purpose |
|-------|---------|---------|
| `backend` | `in_memory` | `postgres` or `in_memory` |
| `dsn_env_var` | `DATABASE_URL` | name of the env var holding the DSN |
| `pool_size` | `10` | base connection pool size |
| `pool_max_overflow` | `5` | additional connections above `pool_size` |
| `statement_timeout_ms` | `30000` | per-connection statement timeout |
