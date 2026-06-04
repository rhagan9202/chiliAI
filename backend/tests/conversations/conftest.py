"""Shared fixtures for conversation tests."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from config.schema import DatabaseConfig
from conversations.adapters.postgres import PostgresConversationRepository
from database.runtime import create_connection_provider


@pytest.fixture()
def database_url() -> str:
    """Return the test database DSN, skipping the test when it is unset."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping conversation integration test.")
    return url


@pytest.fixture()
def conversation_pg_repo(
    database_url: str,
) -> Generator[PostgresConversationRepository, None, None]:
    """Construct a Postgres repo and truncate ``conversations`` on teardown."""

    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresConversationRepository(provider)
    try:
        yield repo
    finally:
        with provider.connection() as conn:
            conn.execute("TRUNCATE TABLE conversations")
            conn.commit()
        provider.close()
