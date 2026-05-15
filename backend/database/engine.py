"""psycopg-backed connection pool and provider.

psycopg is imported lazily via ``importlib`` so this module imports cleanly
and type-checks even when the optional ``[postgres]`` extra is absent — the
same pattern used by ``graph/adapters/neo4j_adapter.py``.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Generator
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

    pool_factory: Callable[..., _ConnectionPoolProtocol] = cast(
        "Callable[..., _ConnectionPoolProtocol]", pool_module.ConnectionPool
    )
    statement_timeout_ms = config.statement_timeout_ms

    def _configure(conn: DatabaseConnection) -> None:
        """Apply session settings to every connection handed out by the pool.

        The commit() is required: a session-level SET inside an open
        transaction is reverted on rollback, and psycopg_pool will not
        accept a connection left mid-transaction. Committing persists the
        statement_timeout and returns the connection to IDLE status.
        """
        conn.execute(f"SET statement_timeout = {statement_timeout_ms}")
        conn.commit()

    try:
        pool = pool_factory(
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
    def connection(self) -> Generator[DatabaseConnection, None, None]:
        with self._pool.connection() as conn:
            yield cast(DatabaseConnection, conn)

    def close(self) -> None:
        self._pool.close()


__all__ = [
    "PsycopgConnectionProvider",
    "create_connection_pool",
]
