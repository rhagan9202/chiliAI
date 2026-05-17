"""Adapter-level protocols for monitoring inputs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from monitoring.models import AlertHistoryRecord, MonitoringBatch
from shared.types import Alert


@runtime_checkable
class ObservationSourceProtocol(Protocol):
    """Load a monitoring batch for evaluation."""

    # TODO(production): Extend with streaming and real-time observation sources:
    # - stream_observations(kb_id) -> AsyncIterator[MonitoringObservation]
    # - get_latest(entity_id, metric_name) -> MonitoringObservation
    # - query_observations(filters) -> list[MonitoringObservation]
    # Implement production adapters sourcing from time-series DB, Kafka, or
    # in-graph computed metrics.

    def load_batch(self, *, knowledge_base_id: str, batch_id: str) -> MonitoringBatch: ...


@runtime_checkable
class ObservationWriter(Protocol):
    """Persist scored observations to the analytics-facing observations store.

    The read-side ``ObservationSourceProtocol`` adapter is added in Plan C;
    this write-side protocol is what the worker's Flow 1 handler depends on.
    """

    def write_observations(
        self, batch: MonitoringBatch, *, correlation_id: str
    ) -> int:
        """Persist a batch's observations idempotently; return the row count written."""
        ...


@runtime_checkable
class AlertHistoryWriter(Protocol):
    """Persist alerts to the analytics-facing ``alert_history`` log."""

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        """Persist alert rows idempotently; return the count of newly written rows."""
        ...

    def count_open_alerts(
        self, *, knowledge_base_id: str, entity_id: str
    ) -> int:
        """Return how many ``open`` alerts the log holds for one entity."""
        ...


@runtime_checkable
class AlertRepositoryProtocol(Protocol):
    """Persist and list alert read models for alert lifecycle operations."""

    def all(self) -> list[Alert]: ...

    def get(self, alert_id: str) -> Alert | None: ...

    def put(self, alert: Alert) -> None: ...


__all__ = [
    "AlertHistoryWriter",
    "AlertRepositoryProtocol",
    "ObservationSourceProtocol",
    "ObservationWriter",
]
