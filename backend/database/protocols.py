"""Connection protocols for the database module.

Consumers depend on these structural protocols rather than importing psycopg
directly. Real psycopg ``Connection`` / ``Cursor`` objects satisfy them.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

Row = tuple[object, ...]
"""A database row as a positional tuple of column values."""


@runtime_checkable
class DatabaseCursor(Protocol):
    """A cursor over a result set."""

    rowcount: int

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> DatabaseCursor: ...

    def fetchone(self) -> Row | None: ...

    def fetchall(self) -> list[Row]: ...

    def close(self) -> None: ...

    def __iter__(self) -> Iterator[Row]: ...


@runtime_checkable
class DatabaseConnection(Protocol):
    """A single database connection."""

    def cursor(self) -> DatabaseCursor: ...

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> DatabaseCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@runtime_checkable
class ConnectionProvider(Protocol):
    """Hands out pooled database connections."""

    def connection(self) -> AbstractContextManager[DatabaseConnection]: ...

    def close(self) -> None: ...


__all__ = [
    "ConnectionProvider",
    "DatabaseConnection",
    "DatabaseCursor",
    "Row",
]
