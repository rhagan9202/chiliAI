"""In-memory observation source for tests and local development."""

from __future__ import annotations

from monitoring.models import AlertHistoryRecord, MonitoringBatch
from shared.types import Alert

__all__ = ["InMemoryAlertHistoryWriter", "InMemoryAlertRepository", "InMemoryObservationSource", "InMemoryObservationWriter"]


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


class InMemoryObservationWriter:
    """An ``ObservationWriter`` that records written batches in memory."""

    def __init__(self) -> None:
        self.written: list[tuple[MonitoringBatch, str]] = []

    def write_observations(
        self, batch: MonitoringBatch, *, correlation_id: str
    ) -> int:
        self.written.append((batch, correlation_id))
        return len(batch.observations)


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


class InMemoryAlertHistoryWriter:
    """An ``AlertHistoryWriter`` that records alert rows in memory."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], AlertHistoryRecord] = {}

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        written = 0
        for record in records:
            key = (record.knowledge_base_id, record.alert_id)
            if key in self._records:
                continue
            self._records[key] = record
            written += 1
        return written

    def count_open_alerts(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> int:
        return sum(
            1
            for record in self._records.values()
            if record.knowledge_base_id == knowledge_base_id
            and record.entity_id == entity_id
            and record.status == "open"
        )
