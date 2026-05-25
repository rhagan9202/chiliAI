"""Tests for the database module exception hierarchy."""

from __future__ import annotations

from database.exceptions import (
    DatabaseConnectionError,
    DatabaseError,
    MigrationError,
    QueryError,
)


def test_all_errors_subclass_database_error() -> None:
    assert issubclass(DatabaseConnectionError, DatabaseError)
    assert issubclass(MigrationError, DatabaseError)
    assert issubclass(QueryError, DatabaseError)


def test_database_error_is_an_exception() -> None:
    assert issubclass(DatabaseError, Exception)


def test_errors_carry_a_message() -> None:
    error = QueryError("failed to run query")
    assert str(error) == "failed to run query"
