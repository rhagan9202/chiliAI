"""Integration tests for the psycopg connection provider."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config.schema import DatabaseConfig
from database.engine import create_connection_pool, PsycopgConnectionProvider
from database.exceptions import DatabaseConnectionError

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
