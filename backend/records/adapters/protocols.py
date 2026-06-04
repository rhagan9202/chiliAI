"""Adapter-level protocols for the records module."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from records.models import RawRecord


@runtime_checkable
class RawRecordStore(Protocol):
    """Persist and read back canonical structured records."""

    def persist(self, records: list[RawRecord]) -> int:
        """Persist records idempotently; return the count of newly inserted rows."""
        ...

    def load_batch(
        self, *, knowledge_base_id: str, correlation_id: str
    ) -> list[RawRecord]:
        """Return all records landed under one ingest run, ordered deterministically."""
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


@runtime_checkable
class RecordSourceProtocol(Protocol):
    """Parse raw submission bytes into a list of record rows."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]: ...


__all__ = [
    "RawRecordStore",
    "RecordSourceProtocol",
]
