"""In-memory observation source for tests and local development."""

from __future__ import annotations

from monitoring.models import AlertHistoryRecord, MonitoringBatch
from shared.types import Alert
from shared.utils import utc_now

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

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        before = len(self.written)
        self.written = [
            (batch, corr_id)
            for batch, corr_id in self.written
            if batch.knowledge_base_id != knowledge_base_id
        ]
        return before - len(self.written)


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

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        keys_to_delete = [
            key for key in self._records if key[0] == knowledge_base_id
        ]
        for key in keys_to_delete:
            del self._records[key]
        return len(keys_to_delete)

    def list_alerts(
        self,
        *,
        statuses: list[str] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AlertHistoryRecord], int]:
        status_set = set(statuses) if statuses else None
        filtered = [
            record
            for record in self._records.values()
            if status_set is None or record.status in status_set
        ]
        ordered = sorted(
            filtered,
            key=lambda record: (record.created_at, record.alert_id),
            reverse=True,
        )
        total = len(ordered)
        return ordered[offset : offset + limit], total

    def get_alert(self, alert_id: str) -> AlertHistoryRecord | None:
        for record in self._records.values():
            if record.alert_id == alert_id:
                return record
        return None

    def acknowledge(self, alert_id: str) -> AlertHistoryRecord | None:
        for key, record in self._records.items():
            if record.alert_id == alert_id:
                updated = record.model_copy(
                    update={"status": "acknowledged", "updated_at": utc_now()}
                )
                self._records[key] = updated
                return updated
        return None

    def count_by_statuses(self, statuses: set[str]) -> int:
        return sum(
            1 for record in self._records.values() if record.status in statuses
        )
