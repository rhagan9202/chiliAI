"""Tests for the psycopg connection provider.

Tests marked `integration` need a real Postgres instance (DATABASE_URL).
Pure unit tests below do not require one.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config.schema import DatabaseConfig
from database.engine import create_connection_pool, PsycopgConnectionProvider
from database.exceptions import DatabaseConnectionError
from database.protocols import DatabaseConnection

pytestmark = pytest.mark.integration


def test_connection_pool_uses_configured_pool_size_as_min_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_kwargs: dict[str, object] = {}

    class FakePool:
        def __init__(self, dsn: str, **kwargs: object) -> None:
            del dsn
            captured_kwargs.update(kwargs)

        def open(self, wait: bool = False, timeout: float = 0.0) -> None:
            del wait, timeout

        def close(self) -> None:
            pass

    def fake_import_module(module_name: str) -> SimpleNamespace:
        assert module_name == "psycopg_pool"
        return SimpleNamespace(ConnectionPool=FakePool)

    monkeypatch.setattr(
        "database.engine.importlib.import_module",
        fake_import_module,
    )

    create_connection_pool(
        "postgresql+psycopg://user:pass@localhost/db",
        DatabaseConfig(backend="postgres", pool_size=7, pool_max_overflow=3),
    )

    assert captured_kwargs["min_size"] == 7
    assert captured_kwargs["max_size"] == 10


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


def test_pooled_connection_has_statement_timeout(database_url: str) -> None:
    config = DatabaseConfig(backend="postgres", statement_timeout_ms=30000)
    provider = PsycopgConnectionProvider(create_connection_pool(database_url, config))
    try:
        with provider.connection() as conn:
            row = conn.execute("SHOW statement_timeout").fetchone()
            assert row is not None
            assert row[0] == "30s"
    finally:
        provider.close()


# ---------------------------------------------------------------------------
# Unit tests for PsycopgConnectionProvider — do not need a live database.
# These tests cover the configure callback invocation, connection() context
# manager yield, and close() delegation paths that are missed when no
# DATABASE_URL is available.
# ---------------------------------------------------------------------------


def test_pool_configure_callback_is_invoked_on_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configure callback must call execute() and commit() on each connection.

    This exercises lines 68-69 in database/engine.py — the two lines inside
    the _configure inner function that apply the statement_timeout session var.
    """
    configure_calls: list[str] = []
    captured_configure: list[Callable[..., object]] = []

    class _FakeConn:
        def execute(self, sql: str) -> None:
            configure_calls.append(f"execute:{sql}")

        def commit(self) -> None:
            configure_calls.append("commit")

    class _FakePool:
        def __init__(self, dsn: str, **kwargs: object) -> None:
            configure_fn = kwargs.get("configure")
            if callable(configure_fn):
                captured_configure.append(configure_fn)

        def open(self, wait: bool = False, timeout: float = 0.0) -> None:
            # Trigger the configure callback with a fake connection.
            if captured_configure:
                captured_configure[0](_FakeConn())

        def close(self) -> None:
            pass

    def _fake_import_pool(module_name: str) -> SimpleNamespace:
        assert module_name == "psycopg_pool"
        return SimpleNamespace(ConnectionPool=_FakePool)

    monkeypatch.setattr(
        "database.engine.importlib.import_module",
        _fake_import_pool,
    )

    create_connection_pool(
        "postgresql://user:pass@host/db",
        DatabaseConfig(backend="postgres", statement_timeout_ms=5000),
    )

    assert any("SET statement_timeout = 5000" in c for c in configure_calls)
    assert "commit" in configure_calls


def test_psycopg_connection_provider_connection_context_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """connection() must yield the connection from the pool's context manager.

    This covers lines 91 and 95-96 in database/engine.py.
    """
    fake_conn = MagicMock(spec=DatabaseConnection)

    class _FakePoolCtxMgr:
        def __enter__(self) -> DatabaseConnection:
            return fake_conn

        def __exit__(self, *args: object) -> None:
            pass

    fake_pool = MagicMock()
    fake_pool.connection.return_value = _FakePoolCtxMgr()

    provider = PsycopgConnectionProvider(fake_pool)

    with provider.connection() as conn:
        result = conn

    assert result is fake_conn


def test_psycopg_connection_provider_close_delegates_to_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close() must call pool.close() exactly once — covers line 99."""
    fake_pool = MagicMock()

    provider = PsycopgConnectionProvider(fake_pool)
    provider.close()

    fake_pool.close.assert_called_once()


def test_create_connection_pool_wraps_open_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any exception from pool.open() must be re-raised as DatabaseConnectionError."""

    class _ExplodingPool:
        def __init__(self, dsn: str, **kwargs: object) -> None:
            configure_fn = kwargs.get("configure")
            if callable(configure_fn):
                configure_fn(_SkipConn())

        def open(self, wait: bool = False, timeout: float = 0.0) -> None:
            raise ConnectionRefusedError("host unreachable")

        def close(self) -> None:
            pass

    class _SkipConn:
        def execute(self, sql: str) -> None:
            pass

        def commit(self) -> None:
            pass

    def _fake_import_exploding(module_name: str) -> SimpleNamespace:
        assert module_name == "psycopg_pool"
        return SimpleNamespace(ConnectionPool=_ExplodingPool)

    monkeypatch.setattr(
        "database.engine.importlib.import_module",
        _fake_import_exploding,
    )

    with pytest.raises(DatabaseConnectionError, match="Failed to open"):
        create_connection_pool(
            "postgresql://user:pass@host/db",
            DatabaseConfig(backend="postgres"),
        )
