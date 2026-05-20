# Module: database

**Verified against codebase:** 2026-05-20
**Source:** `backend/database/`

## Purpose

Postgres + TimescaleDB connection provider. Owns pooled connection management and Alembic-managed schema migrations. All analytics and monitoring modules that need SQL access depend on this module's `ConnectionProvider` protocol.

Shipped as Plan A of the persistence initiative (PR #5, 2026-05-15).

---

## Protocols (`database/protocols.py`)

```python
Row = tuple[object, ...]

class DatabaseCursor(Protocol):
    rowcount: int
    def execute(self, query: str, params: tuple[object, ...] | None = None) -> DatabaseCursor: ...
    def fetchone(self) -> Row | None: ...
    def fetchall(self) -> list[Row]: ...
    def close(self) -> None: ...
    def __iter__(self) -> Iterator[Row]: ...

class DatabaseConnection(Protocol):
    def cursor(self) -> DatabaseCursor: ...
    def execute(self, query: str, params: tuple[object, ...] | None = None) -> DatabaseCursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...

class ConnectionProvider(Protocol):
    def connection(self) -> AbstractContextManager[DatabaseConnection]: ...
    def close(self) -> None: ...
```

---

## Factory (`database/runtime.py`)

```python
def create_connection_provider(config: DatabaseConfig) -> ConnectionProvider | None:
```
- Returns `None` when `config.backend == "in_memory"` — callers fall back to their in-memory adapters.
- Raises `DatabaseConnectionError` when `backend == "postgres"` but `dsn_env_var` env var is not set.
- Builds `PsycopgConnectionProvider` backed by a `psycopg_pool.ConnectionPool`.

---

## Engine (`database/engine.py`)

`PsycopgConnectionProvider` — psycopg 3 pool-backed connection provider. psycopg is lazily imported via `importlib` to allow the module to import cleanly without the `[postgres]` optional extra installed.

---

## Readiness Probe (`database/health.py`)

```python
def check_database_health(provider: ConnectionProvider) -> ...:
```
Executes a lightweight `SELECT 1` to verify the connection pool is reachable.

---

## Migrations

- Alembic config: `backend/alembic.ini` (points `script_location` → `database/migrations/`)
- `database/migrations/` — Alembic `env.py` + versioned raw-SQL migration files
- Current migrations: `0001_persistence_baseline.py`

Schema owned by migrations (partial list):
- `raw_records` table — structured record landing zone
- `risk_history` hypertable (TimescaleDB) — risk score history
- `entity_metrics` hypertable — entity metric observations
- `alert_history` table — persisted alert records

---

## Module Dependencies

- `config/schema.py` — `DatabaseConfig`
- `shared/` — utilities, logging
- Optional: `psycopg`, `psycopg_pool` (skipped without `[postgres]` extra)

---

## Tests

Location: `backend/tests/database/`
Integration tests marked `@pytest.mark.integration` — require a running Postgres instance.
