"""Adapter-level protocols for monitoring inputs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from monitoring.models import MonitoringBatch
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
class AlertRepositoryProtocol(Protocol):
    """Persist and list alert read models for alert lifecycle operations."""

    def all(self) -> list[Alert]: ...

    def get(self, alert_id: str) -> Alert | None: ...

    def put(self, alert: Alert) -> None: ...


__all__ = [
    "AlertRepositoryProtocol",
    "ObservationSourceProtocol",
]