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
BL-041). Head is `0009` — 13 tables total.

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

**Status:** the script, Makefile targets, and CI job are implemented and
merged on this branch. Generating the initial committed snapshot at head
`0009` and a live pass of `make migrate-check` / the CI job require a
Docker-capable environment and are deferred to a follow-up verification pass
in this sprint — `backend/database/migrations/snapshots/head.sql` does not
exist yet, so the CI job currently fails on a missing file (not drift) until
that snapshot lands. Do not treat the mechanism as proven live until that
pass runs and this note is removed.

## Configuration

`DatabaseConfig` (in the domain config YAML) selects the backend:

| Field | Default | Purpose |
|-------|---------|---------|
| `backend` | `in_memory` | `postgres` or `in_memory` |
| `dsn_env_var` | `DATABASE_URL` | name of the env var holding the DSN |
| `pool_size` | `10` | base connection pool size |
| `pool_max_overflow` | `5` | additional connections above `pool_size` |
| `statement_timeout_ms` | `30000` | per-connection statement timeout |
