"""In-memory observation source for tests and local development."""

from __future__ import annotations

from monitoring.models import MonitoringBatch

__all__ = ["InMemoryObservationSource"]


class InMemoryObservationSource:
    """A seeded source of monitoring batches keyed by knowledge base and batch id."""

    def __init__(self, batches: list[MonitoringBatch] | None = None) -> None:
        self._batches: dict[tuple[str, str], MonitoringBatch] = {}
        for batch in batches or []:
            self.put_batch(batch)

    def put_batch(self, batch: MonitoringBatch) -> None:
        self._batches[(batch.knowledge_base_id, batch.batch_id)] = batch

    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch:
        batch = self._batches.get((knowledge_base_id, batch_id))
        if batch is None:
            raise ValueError(
                f"No monitoring batch registered for knowledge_base_id='{knowledge_base_id}' and batch_id='{batch_id}'."
            )
        return batch