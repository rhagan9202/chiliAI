"""In-memory raw record store for tests and local development."""

from __future__ import annotations

from collections.abc import Sequence

from records.models import RawRecord, RawRecordKey

__all__ = ["InMemoryRawRecordStore"]


class InMemoryRawRecordStore:
    """A dict-backed ``RawRecordStore`` keyed by the table's primary key."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], RawRecord] = {}
        self._submissions: set[tuple[str, str]] = set()

    def persist(self, records: list[RawRecord]) -> list[RawRecordKey]:
        """Insert rows idempotently; return the keys this call actually created."""
        inserted: list[RawRecordKey] = []
        for record in records:
            key = (record.knowledge_base_id, record.record_type, record.record_id)
            if key in self._records:
                continue
            self._records[key] = record
            inserted.append(RawRecordKey(record.record_type, record.record_id))
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

    def load_for_kb(self, *, knowledge_base_id: str) -> list[RawRecord]:
        """Return all records for a knowledge base, ordered deterministically."""
        matches = [
            record
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
        ]
        return sorted(matches, key=lambda record: (record.record_type, record.record_id))

    def count_for_kb(self, knowledge_base_id: str) -> int:
        """Return the number of raw records stored for the given knowledge base."""
        return sum(
            1
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
        )

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all records and submission hashes for a knowledge base.

        Returns the count of raw_records rows removed.
        """
        keys_to_remove = [
            key
            for key, record in self._records.items()
            if record.knowledge_base_id == knowledge_base_id
        ]
        for key in keys_to_remove:
            del self._records[key]
        submission_keys_to_remove = [
            sub_key
            for sub_key in self._submissions
            if sub_key[0] == knowledge_base_id
        ]
        for sub_key in submission_keys_to_remove:
            self._submissions.discard(sub_key)
        return len(keys_to_remove)

    def was_submitted(
        self, *, knowledge_base_id: str, submission_hash: str
    ) -> bool:
        """Return True if this submission hash was already registered for the KB."""
        return (knowledge_base_id, submission_hash) in self._submissions

    def record_submission(
        self, *, knowledge_base_id: str, submission_hash: str, correlation_id: str
    ) -> None:
        """Record that a submission hash has been accepted for a KB."""
        self._submissions.add((knowledge_base_id, submission_hash))

    def discard_submission(
        self, *, knowledge_base_id: str, submission_hash: str
    ) -> None:
        """Forget a submission hash so an identical retry is not a duplicate."""
        self._submissions.discard((knowledge_base_id, submission_hash))

    def delete_records(
        self, *, knowledge_base_id: str, keys: Sequence[RawRecordKey]
    ) -> int:
        """Delete exactly the named rows; return the count removed."""
        removed = 0
        for key in keys:
            stored_key = (knowledge_base_id, key.record_type, key.record_id)
            if self._records.pop(stored_key, None) is not None:
                removed += 1
        return removed
