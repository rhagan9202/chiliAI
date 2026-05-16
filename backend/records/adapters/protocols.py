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


@runtime_checkable
class RecordSourceProtocol(Protocol):
    """Parse raw submission bytes into a list of record rows."""

    def read_rows(self, raw: bytes) -> list[dict[str, object]]: ...


__all__ = [
    "RawRecordStore",
    "RecordSourceProtocol",
]
