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
jsonb NOT NULL DEFAULT '[]'::jsonb` (alerts.36 — feeds the in-progress
alerts-durable-read-model effort so `GET /alerts` can be served from
`alert_history` instead of seeded `ApiState`). Head is `0012` — 15 tables
total (column-only addition, no new table).

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
2026-26) and re-verified through `0011` (BL-047, Sprint 2026-28 B2) — every
migration added since has run `make migrate-snapshot` and committed the
refreshed snapshot in the same commit as the migration, and `make
migrate-check` reports clean replay against the live schema.

**SNAPSHOT PENDING for `0012`:** `scripts/ci_migration_check.sh` requires a
live `docker compose` postgres service (it recreates a scratch database via
`docker compose exec`), which was unavailable in the sandbox that added
migration `0012`. The migration was verified directly against `chili_test`
(`alembic upgrade head` + `tests/database` green) but `snapshots/head.sql`
has **not** been regenerated for `0012` yet — the next environment with
Docker access must run `make migrate-snapshot` and commit the refreshed
snapshot before this gap is closed, or CI's drift check will fail.

## Configuration

`DatabaseConfig` (in the domain config YAML) selects the backend:

| Field | Default | Purpose |
|-------|---------|---------|
| `backend` | `in_memory` | `postgres` or `in_memory` |
| `dsn_env_var` | `DATABASE_URL` | name of the env var holding the DSN |
| `pool_size` | `10` | base connection pool size |
| `pool_max_overflow` | `5` | additional connections above `pool_size` |
| `statement_timeout_ms` | `30000` | per-connection statement timeout |
