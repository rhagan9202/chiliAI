"""Adapter-level protocols for the records module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from collections.abc import Sequence

from records.models import RawRecord, RawRecordKey


@runtime_checkable
class RawRecordStore(Protocol):
    """Persist and read back canonical structured records."""

    def persist(self, records: list[RawRecord]) -> list[RawRecordKey]:
        """Persist records idempotently; return the keys newly inserted.

        Rows whose key already exists are skipped and are *not* returned, so
        the result is exactly the set of rows this call created — the only
        safe scope for undoing it.
        """
        ...

    def load_batch(
        self, *, knowledge_base_id: str, correlation_id: str
    ) -> list[RawRecord]:
        """Return all records landed under one ingest run, ordered deterministically."""
        ...

    def load_for_kb(self, *, knowledge_base_id: str) -> list[RawRecord]:
        """Return all records for a knowledge base, ordered deterministically."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all records for a knowledge base; return the count removed."""
        ...

    def was_submitted(
        self, *, knowledge_base_id: str, submission_hash: str
    ) -> bool:
        """Return True if this submission hash was already registered for the KB."""
        ...

    def record_submission(
        self, *, knowledge_base_id: str, submission_hash: str, correlation_id: str
    ) -> None:
        """Record that a submission hash has been accepted for a KB."""
        ...

    def discard_submission(
        self, *, knowledge_base_id: str, submission_hash: str
    ) -> None:
        """Forget a submission hash so an identical retry is not a duplicate."""
        ...

    def delete_records(
        self, *, knowledge_base_id: str, keys: Sequence[RawRecordKey]
    ) -> int:
        """Delete exactly the named rows; return the count removed.

        Deliberately keyed on row identity rather than correlation id: a
        connector sync run assigns one correlation id and reuses it for every
        page, so a correlation-scoped delete would also remove pages that were
        already persisted and published.
        """
        ...


@runtime_checkable
class RecordSourceProtocol(Protocol):
    """Parse raw submission bytes into a list of record rows."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]: ...


__all__ = [
    "RawRecordStore",
    "RecordSourceProtocol",
]
