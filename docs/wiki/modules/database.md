# Module: database

**Verified against codebase:** 2026-06-16
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
- Current migrations:
  - `0001_persistence_baseline.py`
  - `0002_cases.py`
  - `0003_policy.py`
  - `0004_record_submissions.py`
  - `0005_conversations.py`
  - `0006_entity_derived_signals.py`
  - `0007_case_feedback.py`

Schema owned by migrations (partial list):
- `raw_records` table — structured record landing zone
- `observations` hypertable (TimescaleDB) — scored monitoring observations
- `entity_metric_history` hypertable — entity metric history
- `entity_metrics_current` table — latest entity metric snapshot
- `risk_score_history` table — risk assessment history
- `alert_history` table — persisted alert records
- `cases` table — durable, KB-scoped case management; `feedback_history` added in 0007
- `policy_items` table — durable, KB-scoped policy intelligence
- `record_submissions` table — records submission-level deduplication
- `conversations` table — durable RAG chat persistence
- `entity_derived_signals` table — peer-group z-score risk signals

---

## Module Dependencies

- `config/schema.py` — `DatabaseConfig`
- `shared/` — utilities, logging
- Optional: `psycopg`, `psycopg_pool` (skipped without `[postgres]` extra)

---

## Tests

Location: `backend/tests/database/`
Integration tests marked `@pytest.mark.integration` — require a running Postgres instance.
