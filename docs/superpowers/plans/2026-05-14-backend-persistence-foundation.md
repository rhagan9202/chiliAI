# Backend Persistence Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `database/` infrastructure module (Postgres + TimescaleDB connection provider, config, Alembic migrations for all six persistence tables) so later plans can add structured ingestion and analytics write-back.

**Architecture:** A new dependency-light `database/` module exposes a `ConnectionProvider` protocol backed by a psycopg 3 connection pool, selected from a new `DatabaseConfig`. The entire SQL schema (two TimescaleDB hypertables + four regular tables) is owned by one Alembic migration. No ORM — raw SQL throughout, matching the codebase's strict-typing rules.

**Tech Stack:** Python 3.12, psycopg 3 (sync) + psycopg-pool, Alembic, TimescaleDB (Postgres 16), Pydantic v2, pytest.

**Scope note:** This is Plan A of three. Plan B adds the `records/` structured-ingestion module. Plan C adds per-consumer Postgres adapters and risk/alert/metric write-back. This plan produces working, testable DB infrastructure on its own; it wires no consumers yet.

**Reference spec:** `docs/superpowers/specs/2026-05-14-backend-persistence-design.md`

---

## Conventions

- All commands run from `backend/` unless stated otherwise.
- The `[postgres]` extra is **not** in the default container image. Integration tests are marked `@pytest.mark.integration` and skip when Postgres is unavailable — mirroring `tests/graph/test_neo4j_adapter.py`.
- Run unit tests with `pytest -m "not integration"`; integration tests with `pytest -m integration` against a running TimescaleDB.
- New code must pass `pyright --strict` and `ruff check .`. The `database` package and `tests/database` are added to `tool.pyright.include`.
- `database/engine.py` imports psycopg **lazily** via `importlib` (so the module imports cleanly and typechecks without the `[postgres]` extra) — the same pattern as `graph/adapters/neo4j_adapter.py`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/pyproject.toml` | Add `[postgres]` extra, packaging include, pyright include |
| `backend/database/__init__.py` | Public exports |
| `backend/database/exceptions.py` | `DatabaseError` hierarchy |
| `backend/database/protocols.py` | `ConnectionProvider`, `DatabaseConnection`, `DatabaseCursor` protocols |
| `backend/database/engine.py` | `PsycopgConnectionProvider` + `create_connection_pool` (lazy psycopg) |
| `backend/database/runtime.py` | `create_connection_provider(config)` — config-driven selection |
| `backend/database/health.py` | `check_database_health(provider)` readiness probe |
| `backend/database/migrations/` | Alembic env + the baseline schema migration |
| `backend/config/schema.py` | New `DatabaseConfig`; wired into `DomainConfig` |
| `backend/tests/database/` | Unit + integration tests for the above |
| `docker-compose.dev.yaml` | `postgres` service → TimescaleDB image |
| `backend/config/defaults/medicare_fraud_dev.yaml` | New `database:` section |
| `Makefile` | `migrate` target |
| `backend/database/README.md` | Module README |
| `backend/README.md`, `docs/architecture.md`, `.github/copilot-instructions.md` | Doc updates |

---

## Task 1: Add the `postgres` optional dependency and packaging wiring

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add the `postgres` optional-dependency group**

In `backend/pyproject.toml`, under `[project.optional-dependencies]`, add a new group after the `auth` group:

```toml
postgres = [
    "psycopg[binary]>=3.2",
    "psycopg-pool>=3.2",
    "alembic>=1.13",
]
```

- [ ] **Step 2: Add `database` to the setuptools package list**

In `[tool.setuptools.packages.find]`, add `"database*"` to the `include` list:

```toml
[tool.setuptools.packages.find]
include = ["api*", "agent*", "shared*", "config*", "events*", "storage*",
           "ingestion*", "graph*", "vectorstore*", "embeddings*", "rag*",
           "llm*", "analytics*", "monitoring*", "database*"]
```

- [ ] **Step 3: Add `database` and `tests/database` to the pyright include list**

In `[tool.pyright]`, in the `include` array: insert `"database"` immediately after the `"api/routers/ws.py"` line and before `"events"`:

```toml
    "api/routers/ws.py",
    "database",
    "events",
```

Then insert `"tests/database"` immediately after `"tests/api/test_workflows_router.py"` and before `"tests/e2e"`:

```toml
    "tests/api/test_workflows_router.py",
    "tests/database",
    "tests/e2e",
```

Add only these two entries; leave every other entry untouched.

- [ ] **Step 4: Install the new extra**

Run: `pip install -e ".[dev,postgres]"`
Expected: installs `psycopg`, `psycopg-pool`, `alembic` (and `sqlalchemy` as an Alembic dependency) with no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build: add postgres optional dependency group"
```

---

## Task 2: `database/exceptions.py` — exception hierarchy

**Files:**
- Create: `backend/database/__init__.py`
- Create: `backend/database/exceptions.py`
- Create: `backend/tests/database/__init__.py`
- Create: `backend/tests/database/test_exceptions.py`

- [ ] **Step 1: Create empty package markers**

Create `backend/database/__init__.py` with:

```python
"""Postgres / TimescaleDB persistence infrastructure."""

from __future__ import annotations
```

Create `backend/tests/database/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/database/test_exceptions.py`:

```python
"""Tests for the database module exception hierarchy."""

from __future__ import annotations

from database.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    MigrationError,
    QueryError,
)


def test_all_errors_subclass_database_error() -> None:
    assert issubclass(DatabaseConnectionError, DatabaseError)
    assert issubclass(MigrationError, DatabaseError)
    assert issubclass(QueryError, DatabaseError)


def test_database_error_is_an_exception() -> None:
    assert issubclass(DatabaseError, Exception)


def test_errors_carry_a_message() -> None:
    error = QueryError("failed to run query")
    assert str(error) == "failed to run query"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/database/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'database.exceptions'`.

- [ ] **Step 4: Write the implementation**

Create `backend/database/exceptions.py`:

```python
"""Exception hierarchy for the database module."""

from __future__ import annotations


class DatabaseError(Exception):
    """Base exception for database infrastructure failures."""


class DatabaseConnectionError(DatabaseError):
    """Raised when a database connection or pool cannot be established."""


class MigrationError(DatabaseError):
    """Raised when a schema migration fails to apply."""


class QueryError(DatabaseError):
    """Raised when a SQL statement fails to execute."""


__all__ = [
    "DatabaseConnectionError",
    "DatabaseError",
    "MigrationError",
    "QueryError",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/database/test_exceptions.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/database/__init__.py backend/database/exceptions.py backend/tests/database/__init__.py backend/tests/database/test_exceptions.py
git commit -m "feat: add database module exception hierarchy"
```

---

## Task 3: `DatabaseConfig` schema and `DomainConfig` wiring

**Files:**
- Modify: `backend/config/schema.py`
- Create: `backend/tests/database/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/database/test_config.py`:

```python
"""Tests for DatabaseConfig schema and DomainConfig wiring."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import DatabaseConfig


def test_defaults() -> None:
    config = DatabaseConfig()
    assert config.backend == "in_memory"
    assert config.dsn_env_var == "DATABASE_URL"
    assert config.pool_size == 10
    assert config.pool_max_overflow == 5
    assert config.statement_timeout_ms == 30000


def test_postgres_backend_is_accepted() -> None:
    config = DatabaseConfig(backend="postgres")
    assert config.backend == "postgres"


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DatabaseConfig(backend="mysql")  # type: ignore[arg-type]


def test_pool_size_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        DatabaseConfig(pool_size=0)


def test_domain_config_defaults_database_section() -> None:
    from tests.config.helpers import minimal_domain_config  # noqa: PLC0415

    config = minimal_domain_config()
    assert config.database is not None
    assert config.database.backend == "in_memory"
```

> **Note:** if `tests/config/helpers.py` with `minimal_domain_config` does not exist, replace the last test with one that loads `config/defaults/medicare_fraud.yaml` via `config.loader.load_config` and asserts `config.database is not None`. Confirm the helper's existence first with `ls tests/config/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/database/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'DatabaseConfig'`.

- [ ] **Step 3: Add `DatabaseConfig` to `config/schema.py`**

In `backend/config/schema.py`, add this class in the "Sub-models" section, immediately after `EventBusConfig`:

```python
class DatabaseConfig(BaseModel):
    """Configuration for selecting the relational / time-series database backend."""

    backend: Literal["postgres", "in_memory"] = "in_memory"
    dsn_env_var: str = "DATABASE_URL"
    pool_size: int = Field(default=10, gt=0)
    pool_max_overflow: int = Field(default=5, ge=0)
    statement_timeout_ms: int = Field(default=30000, gt=0)
```

- [ ] **Step 4: Wire `DatabaseConfig` into `DomainConfig`**

In the `DomainConfig` class body, add the field after `events`:

```python
    events: EventBusConfig | None = None
    database: DatabaseConfig | None = None
```

In the `_validate_cross_references` model validator, add a default-fill line alongside the existing ones (after the `if self.events is None:` block):

```python
        if self.events is None:
            self.events = EventBusConfig()
        if self.database is None:
            self.database = DatabaseConfig()
```

- [ ] **Step 5: Export `DatabaseConfig`**

In the `__all__` list at the bottom of `config/schema.py`, add `"DatabaseConfig"` in alphabetical order (between `"ChunkingConfig"` and `"DomainConfig"`).

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/database/test_config.py -v`
Expected: PASS (5 tests).

- [ ] **Step 7: Run the config test suite to check for regressions**

Run: `pytest tests/config -v`
Expected: PASS (all existing config tests still green).

- [ ] **Step 8: Commit**

```bash
git add backend/config/schema.py backend/tests/database/test_config.py
git commit -m "feat: add DatabaseConfig to the domain configuration schema"
```

---

## Task 4: `database/protocols.py` — connection protocols

**Files:**
- Create: `backend/database/protocols.py`
- Create: `backend/tests/database/test_protocols.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/database/test_protocols.py`:

```python
"""Tests for the database connection protocols."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from collections.abc import Iterator

from database.protocols import ConnectionProvider, DatabaseConnection, DatabaseCursor


class _FakeCursor:
    def __init__(self) -> None:
        self.rowcount = 0

    def execute(
        self, query: str, params: tuple[object, ...] | None = None
    ) -> "_FakeCursor":
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        return []

    def close(self) -> None:
        return None

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        return iter([])


class _FakeConnection:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def execute(
        self, query: str, params: tuple[object, ...] | None = None
    ) -> _FakeCursor:
        return _FakeCursor()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class _FakeProvider:
    @contextmanager
    def connection(self) -> Iterator[_FakeConnection]:
        yield _FakeConnection()

    def close(self) -> None:
        return None


def test_fake_provider_satisfies_protocol() -> None:
    provider: ConnectionProvider = _FakeProvider()
    with provider.connection() as conn:
        connection: DatabaseConnection = conn
        cursor: DatabaseCursor = connection.cursor()
        assert cursor.fetchall() == []
    provider.close()


def test_connection_returns_context_manager() -> None:
    provider: ConnectionProvider = _FakeProvider()
    result = provider.connection()
    assert isinstance(result, AbstractContextManager)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/database/test_protocols.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'database.protocols'`.

- [ ] **Step 3: Write the implementation**

Create `backend/database/protocols.py`:

```python
"""Connection protocols for the database module.

Consumers depend on these structural protocols rather than importing psycopg
directly. Real psycopg ``Connection`` / ``Cursor`` objects satisfy them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

Row = tuple[object, ...]
"""A database row as a positional tuple of column values."""


@runtime_checkable
class DatabaseCursor(Protocol):
    """A cursor over a result set."""

    rowcount: int

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> DatabaseCursor: ...

    def fetchone(self) -> Row | None: ...

    def fetchall(self) -> list[Row]: ...

    def close(self) -> None: ...

    def __iter__(self) -> Iterator[Row]: ...


@runtime_checkable
class DatabaseConnection(Protocol):
    """A single database connection."""

    def cursor(self) -> DatabaseCursor: ...

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> DatabaseCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class ConnectionProvider(Protocol):
    """Hands out pooled database connections."""

    def connection(self) -> AbstractContextManager[DatabaseConnection]: ...

    def close(self) -> None: ...


__all__ = [
    "ConnectionProvider",
    "DatabaseConnection",
    "DatabaseCursor",
    "Row",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/database/test_protocols.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Type-check**

Run: `pyright database/protocols.py tests/database/test_protocols.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/database/protocols.py backend/tests/database/test_protocols.py
git commit -m "feat: add database connection protocols"
```

---

## Task 5: `database/engine.py` — psycopg connection provider

**Files:**
- Create: `backend/database/engine.py`
- Create: `backend/tests/database/conftest.py`
- Create: `backend/tests/database/test_engine.py`

- [ ] **Step 1: Create the integration-test fixture module**

Create `backend/tests/database/conftest.py`:

```python
"""Shared fixtures for database integration tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def database_url() -> str:
    """Return the test database DSN, skipping the test when it is unset."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping database integration test.")
    return url
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/database/test_engine.py`:

```python
"""Integration tests for the psycopg connection provider."""

from __future__ import annotations

import pytest

from config.schema import DatabaseConfig
from database.engine import create_connection_pool, PsycopgConnectionProvider
from database.exceptions import DatabaseConnectionError

pytestmark = pytest.mark.integration


def test_provider_runs_a_query(database_url: str) -> None:
    config = DatabaseConfig(backend="postgres")
    provider = PsycopgConnectionProvider(create_connection_pool(database_url, config))
    try:
        with provider.connection() as conn:
            cursor = conn.execute("SELECT 1")
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == 1
    finally:
        provider.close()


def test_bad_dsn_raises_database_connection_error() -> None:
    config = DatabaseConfig(backend="postgres")
    with pytest.raises(DatabaseConnectionError):
        create_connection_pool(
            "postgresql://chili:wrong@127.0.0.1:1/nonexistent", config
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/database/test_engine.py -v -m integration`
Expected: FAIL — `ModuleNotFoundError: No module named 'database.engine'` (or skip if `DATABASE_URL` is unset; set it first for this task — see Step 6).

- [ ] **Step 4: Write the implementation**

Create `backend/database/engine.py`:

```python
"""psycopg-backed connection pool and provider.

psycopg is imported lazily via ``importlib`` so this module imports cleanly
and type-checks even when the optional ``[postgres]`` extra is absent — the
same pattern used by ``graph/adapters/neo4j_adapter.py``.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol, cast

from config.schema import DatabaseConfig
from database.exceptions import DatabaseConnectionError
from database.protocols import DatabaseConnection


class _PoolContextManager(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(self, *args: object) -> bool | None: ...


class _ConnectionPoolProtocol(Protocol):
    """Structural subset of ``psycopg_pool.ConnectionPool`` used here."""

    def connection(self) -> _PoolContextManager: ...

    def open(self, wait: bool = ..., timeout: float = ...) -> None: ...

    def close(self) -> None: ...


def _normalize_dsn(dsn: str) -> str:
    """Strip any SQLAlchemy-style ``+driver`` suffix from a Postgres DSN."""

    return dsn.replace("postgresql+psycopg://", "postgresql://", 1)


def create_connection_pool(dsn: str, config: DatabaseConfig) -> _ConnectionPoolProtocol:
    """Build and open a psycopg connection pool.

    Raises ``DatabaseConnectionError`` if the pool cannot connect.
    """

    try:
        pool_module = importlib.import_module("psycopg_pool")
    except ImportError as exc:  # pragma: no cover - extra not installed
        raise DatabaseConnectionError(
            "The 'postgres' optional dependency group is not installed."
        ) from exc

    pool_factory = cast("type[_ConnectionPoolProtocol]", pool_module.ConnectionPool)
    statement_timeout_ms = config.statement_timeout_ms

    def _configure(conn: DatabaseConnection) -> None:
        conn.execute(f"SET statement_timeout = {statement_timeout_ms}")

    try:
        pool = pool_factory(  # type: ignore[call-arg]
            _normalize_dsn(dsn),
            min_size=1,
            max_size=config.pool_size + config.pool_max_overflow,
            open=False,
            configure=_configure,
        )
        pool.open(wait=True, timeout=10.0)
    except Exception as exc:
        raise DatabaseConnectionError(
            "Failed to open the database connection pool."
        ) from exc
    return pool


class PsycopgConnectionProvider:
    """A ``ConnectionProvider`` backed by a psycopg connection pool."""

    def __init__(self, pool: _ConnectionPoolProtocol) -> None:
        self._pool = pool

    @contextmanager
    def connection(self) -> Iterator[DatabaseConnection]:
        with self._pool.connection() as conn:
            yield cast(DatabaseConnection, conn)

    def close(self) -> None:
        self._pool.close()


__all__ = [
    "PsycopgConnectionProvider",
    "create_connection_pool",
]
```

> **Note on `pool_factory(...)`:** psycopg-pool's `ConnectionPool` constructor accepts `min_size`, `max_size`, `open`, and `configure` keyword arguments. The `# type: ignore[call-arg]` is because the structural `_ConnectionPoolProtocol` deliberately does not redeclare the constructor signature. If `pyright --strict` reports the ignore is unused, remove it.

- [ ] **Step 5: Run test to verify it passes**

Start TimescaleDB (see Task 10 for the compose change; for now a quick container works):

```bash
docker run -d --name chili-tsdb-test -e POSTGRES_DB=chili -e POSTGRES_USER=chili \
  -e POSTGRES_PASSWORD=chili -p 5432:5432 timescale/timescaledb:latest-pg16
```

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/database/test_engine.py -v -m integration`
Expected: PASS (2 tests).

- [ ] **Step 6: Type-check**

Run: `pyright database/engine.py tests/database/test_engine.py tests/database/conftest.py`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/database/engine.py backend/tests/database/conftest.py backend/tests/database/test_engine.py
git commit -m "feat: add psycopg connection pool and provider"
```

---

## Task 6: `database/runtime.py` — config-driven provider selection

**Files:**
- Create: `backend/database/runtime.py`
- Modify: `backend/database/__init__.py`
- Create: `backend/tests/database/test_runtime.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/database/test_runtime.py`:

```python
"""Tests for config-driven connection-provider selection."""

from __future__ import annotations

import pytest

from config.schema import DatabaseConfig
from database.exceptions import DatabaseConnectionError
from database.runtime import create_connection_provider


def test_in_memory_backend_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = DatabaseConfig(backend="in_memory")
    assert create_connection_provider(config) is None


def test_postgres_backend_without_dsn_env_var_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = DatabaseConfig(backend="postgres")
    with pytest.raises(DatabaseConnectionError, match="DATABASE_URL"):
        create_connection_provider(config)


@pytest.mark.integration
def test_postgres_backend_builds_a_provider(database_url: str) -> None:
    config = DatabaseConfig(backend="postgres")
    provider = create_connection_provider(config)
    assert provider is not None
    try:
        with provider.connection() as conn:
            assert conn.execute("SELECT 1").fetchone() is not None
    finally:
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/database/test_runtime.py -v -m "not integration"`
Expected: FAIL — `ModuleNotFoundError: No module named 'database.runtime'`.

- [ ] **Step 3: Write the implementation**

Create `backend/database/runtime.py`:

```python
"""Config-driven construction of a database connection provider."""

from __future__ import annotations

import os

from config.schema import DatabaseConfig
from database.engine import PsycopgConnectionProvider, create_connection_pool
from database.exceptions import DatabaseConnectionError
from database.protocols import ConnectionProvider


def create_connection_provider(config: DatabaseConfig) -> ConnectionProvider | None:
    """Build a connection provider for the configured backend.

    Returns ``None`` when ``backend == "in_memory"`` — callers fall back to
    their in-memory adapters. Raises ``DatabaseConnectionError`` when the
    ``postgres`` backend is selected but no DSN is available.
    """

    if config.backend == "in_memory":
        return None

    dsn = os.environ.get(config.dsn_env_var)
    if not dsn:
        raise DatabaseConnectionError(
            f"Database backend is 'postgres' but environment variable "
            f"'{config.dsn_env_var}' is not set."
        )

    pool = create_connection_pool(dsn, config)
    return PsycopgConnectionProvider(pool)


__all__ = [
    "create_connection_provider",
]
```

- [ ] **Step 4: Update `database/__init__.py` with public exports**

Replace the contents of `backend/database/__init__.py` with:

```python
"""Postgres / TimescaleDB persistence infrastructure."""

from __future__ import annotations

from database.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    MigrationError,
    QueryError,
)
from database.protocols import ConnectionProvider, DatabaseConnection, DatabaseCursor, Row
from database.runtime import create_connection_provider

__all__ = [
    "ConnectionProvider",
    "DatabaseConnection",
    "DatabaseConnectionError",
    "DatabaseCursor",
    "DatabaseError",
    "MigrationError",
    "QueryError",
    "Row",
    "create_connection_provider",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/database/test_runtime.py -v -m "not integration"`
Expected: PASS (2 unit tests; the integration test is skipped).

- [ ] **Step 6: Type-check the whole module**

Run: `pyright database`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/database/runtime.py backend/database/__init__.py backend/tests/database/test_runtime.py
git commit -m "feat: add config-driven database provider selection"
```

---

## Task 7: `database/health.py` — readiness probe

**Files:**
- Create: `backend/database/health.py`
- Create: `backend/tests/database/test_health.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/database/test_health.py`:

```python
"""Tests for the database health probe."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

import pytest

from config.schema import DatabaseConfig
from database.health import check_database_health
from database.protocols import DatabaseConnection, DatabaseCursor, Row
from database.runtime import create_connection_provider


class _OkCursor:
    rowcount = 1

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> "_OkCursor":
        return self

    def fetchone(self) -> Row | None:
        return (1,)

    def fetchall(self) -> list[Row]:
        return [(1,)]

    def close(self) -> None:
        return None

    def __iter__(self) -> Iterator[Row]:
        return iter([(1,)])


class _OkConnection:
    def cursor(self) -> DatabaseCursor:
        return _OkCursor()

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> DatabaseCursor:
        return _OkCursor()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class _OkProvider:
    @contextmanager
    def connection(self) -> Iterator[DatabaseConnection]:
        yield _OkConnection()

    def close(self) -> None:
        return None


class _FailingProvider:
    @contextmanager
    def connection(self) -> Iterator[DatabaseConnection]:
        raise RuntimeError("connection refused")
        yield  # pragma: no cover

    def close(self) -> None:
        return None


def test_healthy_provider_returns_true() -> None:
    assert check_database_health(_OkProvider()) is True


def test_failing_provider_returns_false() -> None:
    assert check_database_health(_FailingProvider()) is False


@pytest.mark.integration
def test_real_provider_is_healthy(database_url: str) -> None:
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    try:
        assert check_database_health(provider) is True
    finally:
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/database/test_health.py -v -m "not integration"`
Expected: FAIL — `ModuleNotFoundError: No module named 'database.health'`.

- [ ] **Step 3: Write the implementation**

Create `backend/database/health.py`:

```python
"""Database readiness probe."""

from __future__ import annotations

from database.protocols import ConnectionProvider


def check_database_health(provider: ConnectionProvider) -> bool:
    """Return ``True`` when the database answers a trivial query."""

    try:
        with provider.connection() as conn:
            row = conn.execute("SELECT 1").fetchone()
            return row is not None and row[0] == 1
    except Exception:
        return False


__all__ = [
    "check_database_health",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/database/test_health.py -v -m "not integration"`
Expected: PASS (2 unit tests; integration test skipped).

- [ ] **Step 5: Add `check_database_health` to package exports**

In `backend/database/__init__.py`, add the import and the `__all__` entry:

```python
from database.health import check_database_health
```

and add `"check_database_health"` to `__all__` (alphabetical order).

- [ ] **Step 6: Type-check**

Run: `pyright database`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add backend/database/health.py backend/database/__init__.py backend/tests/database/test_health.py
git commit -m "feat: add database health probe"
```

---

## Task 8: Alembic scaffold

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/database/migrations/__init__.py`
- Create: `backend/database/migrations/env.py`
- Create: `backend/database/migrations/script.py.mako`
- Create: `backend/database/migrations/versions/__init__.py`

- [ ] **Step 1: Create `alembic.ini`**

Create `backend/alembic.ini`:

```ini
[alembic]
script_location = database/migrations
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create the migrations package markers**

Create `backend/database/migrations/__init__.py` (empty file) and `backend/database/migrations/versions/__init__.py` (empty file).

- [ ] **Step 3: Create the Alembic `env.py`**

Create `backend/database/migrations/env.py`:

```python
"""Alembic migration environment.

The schema is written as raw SQL — there are no ORM models, so
``target_metadata`` is ``None`` and autogenerate is unused. The database URL
is read from the ``DATABASE_URL`` environment variable and normalized to the
psycopg 3 dialect.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set to run migrations.")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Create the migration template**

Create `backend/database/migrations/script.py.mako`:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Verify Alembic recognizes the scaffold**

Run: `alembic history`
Expected: succeeds with empty history (no migrations yet), no configuration errors.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/database/migrations
git commit -m "build: scaffold Alembic migration environment"
```

---

## Task 9: Initial migration — the persistence baseline schema

**Files:**
- Create: `backend/database/migrations/versions/0001_persistence_baseline.py`
- Create: `backend/tests/database/test_migrations.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/database/test_migrations.py`:

```python
"""Integration test: the baseline migration creates the full schema."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider

pytestmark = pytest.mark.integration

_BACKEND_DIR = Path(__file__).resolve().parents[2]

_EXPECTED_TABLES = {
    "raw_records",
    "observations",
    "entity_metric_history",
    "entity_metrics_current",
    "risk_score_history",
    "alert_history",
}
_EXPECTED_HYPERTABLES = {"observations", "entity_metric_history"}


def _run_migrations(database_url: str) -> None:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_baseline_migration_creates_all_tables(database_url: str) -> None:
    _run_migrations(database_url)
    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    try:
        with provider.connection() as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ).fetchall()
            tables = {str(row[0]) for row in rows}
            assert _EXPECTED_TABLES.issubset(tables)

            hyper = conn.execute(
                "SELECT hypertable_name FROM timescaledb_information.hypertables"
            ).fetchall()
            hypertables = {str(row[0]) for row in hyper}
            assert _EXPECTED_HYPERTABLES.issubset(hypertables)
    finally:
        provider.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/database/test_migrations.py -v -m integration`
Expected: FAIL — `alembic upgrade head` finds no migrations, so the tables are absent and the assertion fails.

- [ ] **Step 3: Write the baseline migration**

Create `backend/database/migrations/versions/0001_persistence_baseline.py`:

```python
"""Persistence baseline schema.

Creates the six persistence tables from
docs/superpowers/specs/2026-05-14-backend-persistence-design.md §6 and
converts the two time-series tables into TimescaleDB hypertables.

Revision ID: 0001_persistence_baseline
Revises:
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001_persistence_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # --- ingestion: canonical tabular landing zone -------------------------
    op.execute(
        """
        CREATE TABLE raw_records (
            knowledge_base_id text        NOT NULL,
            record_type       text        NOT NULL,
            record_id         text        NOT NULL,
            payload           jsonb       NOT NULL,
            source_type       text        NOT NULL,
            source_ref        text,
            correlation_id    text        NOT NULL,
            content_hash      text        NOT NULL,
            ingested_at       timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, record_type, record_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_raw_records_payload ON raw_records USING gin (payload)")
    op.execute(
        "CREATE INDEX ix_raw_records_correlation "
        "ON raw_records (knowledge_base_id, correlation_id)"
    )

    # --- monitoring: scored observations (hypertable) ----------------------
    op.execute(
        """
        CREATE TABLE observations (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            entity_type       text             NOT NULL,
            metric_name       text             NOT NULL,
            score             double precision NOT NULL,
            observed_at       timestamptz      NOT NULL,
            rationale         text             NOT NULL,
            evidence_pack_id  text,
            batch_id          text             NOT NULL,
            correlation_id    text             NOT NULL,
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at)
        )
        """
    )
    op.execute("SELECT create_hypertable('observations', 'observed_at')")
    op.execute(
        "CREATE INDEX ix_observations_batch "
        "ON observations (knowledge_base_id, batch_id)"
    )

    # --- analytics: graph metrics over time (hypertable) -------------------
    op.execute(
        """
        CREATE TABLE entity_metric_history (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            metric_name       text             NOT NULL,
            value             double precision NOT NULL,
            observed_at       timestamptz      NOT NULL,
            correlation_id    text             NOT NULL,
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name, observed_at)
        )
        """
    )
    op.execute("SELECT create_hypertable('entity_metric_history', 'observed_at')")

    # --- analytics: latest metric snapshot (data table) --------------------
    op.execute(
        """
        CREATE TABLE entity_metrics_current (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            metric_name       text             NOT NULL,
            value             double precision NOT NULL,
            updated_at        timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, entity_id, metric_name)
        )
        """
    )

    # --- analytics: risk assessment history --------------------------------
    op.execute(
        """
        CREATE TABLE risk_score_history (
            knowledge_base_id text             NOT NULL,
            entity_id         text             NOT NULL,
            request_id        text             NOT NULL,
            overall_score     double precision NOT NULL,
            risk_level        text             NOT NULL,
            factors           jsonb            NOT NULL,
            assessed_at       timestamptz      NOT NULL DEFAULT now(),
            PRIMARY KEY (request_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_risk_score_history_entity "
        "ON risk_score_history (knowledge_base_id, entity_id, assessed_at DESC)"
    )

    # --- monitoring: analytics-facing alert log ----------------------------
    op.execute(
        """
        CREATE TABLE alert_history (
            knowledge_base_id text        NOT NULL,
            alert_id          text        NOT NULL,
            entity_id         text        NOT NULL,
            entity_type       text        NOT NULL,
            severity          text        NOT NULL,
            status            text        NOT NULL,
            title             text        NOT NULL,
            reasoning         text        NOT NULL,
            metric_name       text        NOT NULL,
            evidence_pack_id  text,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (knowledge_base_id, alert_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_alert_history_entity "
        "ON alert_history (knowledge_base_id, entity_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_history")
    op.execute("DROP TABLE IF EXISTS risk_score_history")
    op.execute("DROP TABLE IF EXISTS entity_metrics_current")
    op.execute("DROP TABLE IF EXISTS entity_metric_history")
    op.execute("DROP TABLE IF EXISTS observations")
    op.execute("DROP TABLE IF EXISTS raw_records")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/database/test_migrations.py -v -m integration`
Expected: PASS (1 test).

> If `create_hypertable('observations', 'observed_at')` raises a deprecation/signature error on a newer TimescaleDB, switch both `create_hypertable` calls to the dimension-builder form, e.g. `SELECT create_hypertable('observations', by_range('observed_at'))`.

- [ ] **Step 5: Verify the downgrade path**

Run:
```bash
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili alembic downgrade base
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili alembic upgrade head
```
Expected: both succeed; the round trip drops and recreates the schema cleanly.

- [ ] **Step 6: Commit**

```bash
git add backend/database/migrations/versions/0001_persistence_baseline.py backend/tests/database/test_migrations.py
git commit -m "feat: add persistence baseline schema migration"
```

---

## Task 10: Switch the dev-compose Postgres service to TimescaleDB

**Files:**
- Modify: `docker-compose.dev.yaml`

- [ ] **Step 1: Change the `postgres` service image**

In `docker-compose.dev.yaml`, locate the `postgres` service and change:

```yaml
  postgres:
    image: postgres:16-alpine
```

to:

```yaml
  postgres:
    image: timescale/timescaledb:latest-pg16
```

Leave the `ports`, `environment`, `volumes`, `healthcheck`, and `networks` blocks unchanged — the TimescaleDB image is Postgres-compatible and `pg_isready` still works.

- [ ] **Step 2: Verify the stack starts and TimescaleDB is available**

Run (from the repo root):
```bash
docker compose -f docker-compose.dev.yaml up -d postgres
docker compose -f docker-compose.dev.yaml exec postgres \
  psql -U chili -d chili -c "CREATE EXTENSION IF NOT EXISTS timescaledb; SELECT extversion FROM pg_extension WHERE extname='timescaledb';"
```
Expected: prints a TimescaleDB version string (e.g. `2.x.x`).

- [ ] **Step 3: Stop the test container from Task 5 if still running**

Run: `docker rm -f chili-tsdb-test 2>/dev/null || true`

- [ ] **Step 4: Commit**

```bash
git add docker-compose.dev.yaml
git commit -m "build: use TimescaleDB image for the dev postgres service"
```

---

## Task 11: Dev domain config + Makefile migration target

**Files:**
- Modify: `backend/config/defaults/medicare_fraud_dev.yaml`
- Modify: `Makefile`

- [ ] **Step 1: Add a `database` section to the dev config**

In `backend/config/defaults/medicare_fraud_dev.yaml`, add a top-level `database` block. Place it next to the other backend-selection sections (e.g. directly after the `events:` block; if there is no `events:` block, add it before the `ui:` block):

```yaml
database:
  backend: postgres
  dsn_env_var: DATABASE_URL
  pool_size: 10
  pool_max_overflow: 5
  statement_timeout_ms: 30000
```

- [ ] **Step 2: Verify the dev config still loads**

Run (from `backend/`):
```bash
CHILI_CONFIG_PATH=config/defaults/medicare_fraud_dev.yaml CHILI_ENV=local \
  python -c "from config.loader import load_config; c = load_config(); print(c.database)"
```
Expected: prints a `DatabaseConfig` with `backend='postgres'`.

- [ ] **Step 3: Add a `migrate` target to the Makefile**

In `Makefile`, add `migrate` to the `.PHONY` line and add this target in the Development section (after `api-shell`):

```makefile
migrate: ## Run database migrations inside the API container
	$(COMPOSE_DEV) exec api alembic upgrade head
```

- [ ] **Step 4: Verify the migration target runs**

Run (from the repo root, with the dev stack up):
```bash
docker compose -f docker-compose.dev.yaml up -d
make migrate
```
Expected: `alembic upgrade head` reports applying `0001_persistence_baseline` (or "already at head" on a re-run).

- [ ] **Step 5: Commit**

```bash
git add backend/config/defaults/medicare_fraud_dev.yaml Makefile
git commit -m "build: enable postgres backend in dev config and add migrate target"
```

---

## Task 12: Documentation

**Files:**
- Create: `backend/database/README.md`
- Modify: `backend/README.md`
- Modify: `docs/architecture.md`
- Modify: `.github/copilot-instructions.md`

- [ ] **Step 1: Write the module README**

Create `backend/database/README.md`:

```markdown
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
```

- [ ] **Step 2: Update `backend/README.md`**

In `backend/README.md`, in the "What's functional" list, add an entry for the new module (after the `storage/` entry):

```markdown
- **`database/`** — Postgres + TimescaleDB connection provider, `DatabaseConfig`-driven backend selection, and Alembic-managed schema (six persistence tables). Infrastructure only — no domain logic.
```

In the "Target Module Structure" tree, add the line:

```
└── database/        # Postgres + TimescaleDB connection provider, Alembic migrations
```

In the "Environment variables" table, add:

```markdown
| `DATABASE_URL` | unset | Postgres/TimescaleDB DSN. Required when `DatabaseConfig.backend=postgres` and to run Alembic migrations. |
```

- [ ] **Step 3: Update `docs/architecture.md`**

In `docs/architecture.md`:
- In the §5.1 package tree, add `database/` with a one-line note: `# Postgres + TimescaleDB connection provider, Alembic migrations`.
- In the §5.2 module responsibility matrix, add a `database` row: Owns "Connection pooling, schema migrations"; Depends on "`config`, `shared`"; Forbidden "domain logic, business logic, imports of any capability module".
- In §4 container responsibilities, note that the Postgres/TimescaleDB container is now an infrastructure service persisting structured records, observations, metric history, and risk/alert history.

- [ ] **Step 4: Update `.github/copilot-instructions.md`**

In `.github/copilot-instructions.md`, wherever the backend module list / external-systems list appears, add `database/` (Postgres + TimescaleDB, Alembic migrations) so the agent operating rules stay consistent with `CLAUDE.md` and `backend/README.md`.

- [ ] **Step 5: Commit**

```bash
git add backend/database/README.md backend/README.md docs/architecture.md .github/copilot-instructions.md
git commit -m "docs: document the database persistence module"
```

---

## Final Verification

- [ ] **Step 1: Run the full unit suite**

Run (from `backend/`): `pytest -m "not integration"`
Expected: all tests pass; coverage for the `database` package ≥ 85%.

- [ ] **Step 2: Run the database integration suite**

Run: `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili pytest tests/database -m integration -v`
Expected: all integration tests pass against a running TimescaleDB.

- [ ] **Step 3: Type-check**

Run: `pyright database tests/database`
Expected: 0 errors.

- [ ] **Step 4: Lint**

Run: `ruff check database tests/database`
Expected: 0 errors (import-order warnings may be ignored per `CLAUDE.md`).

- [ ] **Step 5: Confirm the dev stack is healthy end to end**

Run (from the repo root):
```bash
docker compose -f docker-compose.dev.yaml up -d
make migrate
```
Expected: the stack starts; `make migrate` applies the baseline schema with no errors.

---

## Plan Self-Review Notes

- **Spec coverage:** §5.1 `database/` module → Tasks 2,4,5,6,7; §6 schema (all 6 tables + 2 hypertables) → Task 9; §7 `DatabaseConfig` → Task 3; §11 error handling (`DatabaseError` hierarchy, fail-fast) → Tasks 2,5,6; §13 packaging + dev compose → Tasks 1,10,11; §14 docs → Task 12. The `records/` module (§5.2), per-consumer adapters (§5.3), events, and worker handlers (§8) are explicitly deferred to Plans B and C.
- **Out of scope for Plan A (carried forward):** `infra/k8s` + Helm Timescale manifests (design §13) — to be handled in Plan C's ops task; production deployment profiles remain future work.
- **Type consistency:** `ConnectionProvider`, `DatabaseConnection`, `DatabaseCursor`, and `Row` are defined once in Task 4 and reused unchanged in Tasks 5–7. `create_connection_provider` returns `ConnectionProvider | None` consistently in Task 6 and its callers.
