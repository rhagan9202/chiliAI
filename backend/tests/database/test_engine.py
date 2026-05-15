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
