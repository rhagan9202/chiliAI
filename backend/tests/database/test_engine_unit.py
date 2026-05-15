"""Unit tests for database.engine helpers (no database required)."""

from __future__ import annotations

import pytest

from database.engine import _normalize_dsn  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("dsn", "expected"),
    [
        ("postgresql+psycopg://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgresql://u:p@h:5432/db", "postgresql://u:p@h:5432/db"),
        ("postgresql+psycopg://h/db", "postgresql://h/db"),
    ],
)
def test_normalize_dsn(dsn: str, expected: str) -> None:
    assert _normalize_dsn(dsn) == expected
