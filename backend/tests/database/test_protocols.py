"""Tests for the database connection protocols."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from collections.abc import Generator, Iterator

from database.protocols import ConnectionProvider, DatabaseConnection, DatabaseCursor


class _FakeCursor:
    def __init__(self) -> None:
        self.rowcount = 0

    def execute(
        self, query: str, params: tuple[object, ...] | None = None
    ) -> "_FakeCursor":
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return None

    def fetchall(self) -> list[tuple[object, ...]]:
        return []

    def close(self) -> None:
        return None

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        return iter([])


class _FakeConnection:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def execute(
        self, query: str, params: tuple[object, ...] | None = None
    ) -> _FakeCursor:
        return _FakeCursor()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class _FakeProvider:
    @contextmanager
    def connection(self) -> Generator[_FakeConnection, None, None]:
        yield _FakeConnection()

    def close(self) -> None:
        return None


def test_fake_provider_satisfies_protocol() -> None:
    provider: ConnectionProvider = _FakeProvider()
    with provider.connection() as conn:
        connection: DatabaseConnection = conn
        cursor: DatabaseCursor = connection.cursor()
        assert cursor.fetchall() == []
    provider.close()


def test_connection_returns_context_manager() -> None:
    provider: ConnectionProvider = _FakeProvider()
    result = provider.connection()
    assert isinstance(result, AbstractContextManager)
