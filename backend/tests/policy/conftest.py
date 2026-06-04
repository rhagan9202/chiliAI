"""Shared fixtures for policy tests."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from config.schema import DatabaseConfig
from database.runtime import create_connection_provider
from policy.adapters.postgres import PostgresPolicyItemRepository


@pytest.fixture()
def database_url() -> str:
    """Return the test database DSN, skipping the test when it is unset."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping policy integration test.")
    return url


@pytest.fixture()
def policy_pg_repo(database_url: str) -> Generator[PostgresPolicyItemRepository, None, None]:
    """Construct a ``PostgresPolicyItemRepository`` and truncate ``policy_items`` on teardown."""

    provider = create_connection_provider(DatabaseConfig(backend="postgres"))
    assert provider is not None
    repo = PostgresPolicyItemRepository(provider)
    try:
        yield repo
    finally:
        with provider.connection() as conn:
            conn.execute("TRUNCATE TABLE policy_items")
            conn.commit()
        provider.close()
