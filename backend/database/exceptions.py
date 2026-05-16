"""Exception hierarchy for the database module."""

from __future__ import annotations


class DatabaseError(Exception):
    """Base exception for database infrastructure failures."""


class DatabaseConnectionError(DatabaseError):
    """Raised when a database connection or pool cannot be established."""


class MigrationError(DatabaseError):
    """Raised when a schema migration fails to apply."""


class QueryError(DatabaseError):
    """Raised when a SQL statement fails to execute."""


__all__ = [
    "DatabaseConnectionError",
    "DatabaseError",
    "MigrationError",
    "QueryError",
]
