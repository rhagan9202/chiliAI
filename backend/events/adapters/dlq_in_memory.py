"""In-memory DLQ record store for tests and local scaffolding (BL-023)."""

from __future__ import annotations

from events.dlq_models import DlqRecord, DlqRecordStatus
from events.protocols import DlqRecordStore
from shared.utils import utc_now

__all__ = ["InMemoryDlqRecordStore"]


class InMemoryDlqRecordStore(DlqRecordStore):
    """Process-local DLQ record ledger mirroring the Postgres adapter contract."""

    def __init__(self) -> None:
        self._records: dict[str, DlqRecord] = {}

    def persist(self, record: DlqRecord) -> DlqRecord:
        # Upsert by dlq_id: a repeat persist() for an existing id replaces the
        # stored record in place rather than appending a second entry (see
        # events.protocols.DlqRecordStore.persist). Terminal-state guard: a
        # stored record that is already replayed/discarded is never reverted
        # back to pending — return it unchanged instead.
        existing = self._records.get(record.dlq_id)
        if existing is not None and existing.status != "pending":
            return existing
        self._records[record.dlq_id] = record
        return record

    def list(
        self,
        *,
        status: DlqRecordStatus | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DlqRecord], int]:
        matched = [
            record
            for record in self._records.values()
            if (status is None or record.status == status)
            and (event_type is None or record.event_type == event_type)
        ]
        # Deterministic newest-first ordering: (created_at DESC, dlq_id DESC),
        # matching the Postgres adapter's ORDER BY.
        matched.sort(key=lambda record: (record.created_at, record.dlq_id), reverse=True)
        return matched[offset : offset + limit], len(matched)

    def get(self, dlq_id: str) -> DlqRecord | None:
        return self._records.get(dlq_id)

    def mark_replayed(self, dlq_id: str) -> DlqRecord | None:
        return self._transition(dlq_id, "replayed", stamp_replayed=True)

    def mark_discarded(self, dlq_id: str) -> DlqRecord | None:
        return self._transition(dlq_id, "discarded", stamp_replayed=False)

    def _transition(
        self, dlq_id: str, status: DlqRecordStatus, *, stamp_replayed: bool
    ) -> DlqRecord | None:
        existing = self._records.get(dlq_id)
        if existing is None or existing.status != "pending":
            return None
        updated = existing.model_copy(
            update={
                "status": status,
                "replayed_at": utc_now() if stamp_replayed else None,
            }
        )
        self._records[dlq_id] = updated
        return updated
