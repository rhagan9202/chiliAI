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
