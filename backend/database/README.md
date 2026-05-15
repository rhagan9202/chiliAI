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

Six tables (see `docs/architecture.md` and the design spec for details):
`raw_records`, `observations` (hypertable), `entity_metric_history`
(hypertable), `entity_metrics_current`, `risk_score_history`, `alert_history`.

## Commands

```bash
pip install -e ".[dev,postgres]"     # install the optional extra
alembic upgrade head                 # apply migrations (needs DATABASE_URL)
alembic downgrade base               # drop the schema
pytest tests/database -m "not integration"   # fast unit tests
pytest tests/database -m integration          # needs a running TimescaleDB
```

## Configuration

`DatabaseConfig` (in the domain config YAML) selects the backend:

| Field | Default | Purpose |
|-------|---------|---------|
| `backend` | `in_memory` | `postgres` or `in_memory` |
| `dsn_env_var` | `DATABASE_URL` | name of the env var holding the DSN |
| `pool_size` | `10` | base connection pool size |
| `pool_max_overflow` | `5` | additional connections above `pool_size` |
| `statement_timeout_ms` | `30000` | per-connection statement timeout |
