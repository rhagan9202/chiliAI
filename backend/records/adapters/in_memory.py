"""In-memory raw record store for tests and local development."""

from __future__ import annotations

from records.models import RawRecord

__all__ = ["InMemoryRawRecordStore"]


class InMemoryRawRecordStore:
    """A dict-backed ``RawRecordStore`` keyed by the table's primary key."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], RawRecord] = {}

    def persist(self, records: list[RawRecord]) -> int:
        inserted = 0
        for record in records:
            key = (record.knowledge_base_id, record.record_type, record.record_id)
            if key in self._records:
                continue
            self._records[key] = record
            inserted += 1
        return inserted

    def load_batch(
        self, *, knowledge_base_id: str, correlation_id: str
    ) -> list[RawRecord]:
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.correlation_id == correlation_id
        ]
        return sorted(matches, key=lambda record: (record.record_type, record.record_id))
