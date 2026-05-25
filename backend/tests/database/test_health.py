"""Tests for the database health probe."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Generator, Iterator

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
    def connection(self) -> Generator[DatabaseConnection, None, None]:
        yield _OkConnection()

    def close(self) -> None:
        return None


class _FailingProvider:
    @contextmanager
    def connection(self) -> Generator[DatabaseConnection, None, None]:
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
