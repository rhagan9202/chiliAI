"""In-memory observation source for tests and local development."""

from __future__ import annotations

from monitoring.models import MonitoringBatch
from shared.types import Alert

__all__ = ["InMemoryAlertRepository", "InMemoryObservationSource"]


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


class InMemoryAlertRepository:
    """A simple in-memory store of alerts keyed by alert id.

    Insertion order is preserved so list operations are deterministic.
    """

    def __init__(self, alerts: list[Alert] | None = None) -> None:
        self._alerts: dict[str, Alert] = {}
        for alert in alerts or []:
            self.put(alert)

    def put(self, alert: Alert) -> None:
        self._alerts[alert.id] = alert

    def get(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    def all(self) -> list[Alert]:
        return list(self._alerts.values())