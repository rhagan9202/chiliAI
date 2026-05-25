"""Tests for the records module exception hierarchy."""

from __future__ import annotations

from records.exceptions import (
    RecordFeedNotFoundError,
    RecordMappingError,
    RecordPersistenceError,
    RecordsError,
    RecordValidationError,
)


def test_all_errors_subclass_records_error() -> None:
    assert issubclass(RecordValidationError, RecordsError)
    assert issubclass(RecordPersistenceError, RecordsError)
    assert issubclass(RecordFeedNotFoundError, RecordsError)
    assert issubclass(RecordMappingError, RecordsError)


def test_feed_not_found_error_names_the_feed() -> None:
    error = RecordFeedNotFoundError("claims_feed")
    assert error.feed_name == "claims_feed"
    assert "claims_feed" in str(error)
