"""Shared fixtures for records integration tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def database_url() -> str:
    """Return the test database DSN, skipping the test when it is unset."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set; skipping records integration test.")
    return url
