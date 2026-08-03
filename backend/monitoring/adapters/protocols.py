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

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all observations for a knowledge base; return rows removed."""
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

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all alert history for a knowledge base; return rows removed."""
        ...


@runtime_checkable
class AlertFeedStoreProtocol(Protocol):
    """Durable read/mutate store over the analytics-facing ``alert_history`` log.

    Supersets ``AlertHistoryWriter`` with the read/mutate surface the API's
    alert feed needs (list, get, acknowledge, count). Concrete adapters
    implement both protocols on the same class; ``AlertHistoryWriter``
    remains importable for the worker's existing construction sites.
    """

    def write_alerts(self, records: list[AlertHistoryRecord]) -> int:
        """Persist alert rows idempotently; return the count of newly written rows."""
        ...

    def list_alerts(
        self,
        *,
        knowledge_base_id: str | None = None,
        statuses: list[str] | None = None,
        severities: list[str] | None = None,
        tags: list[str] | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        evidence: str | None = None,
        freshness: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AlertHistoryRecord], int]:
        """Return a page of alerts (created_at DESC, alert_id DESC) and the filtered total.

        ``statuses=None`` and ``statuses=[]`` are equivalent: both mean "no
        status filter requested" and return all alerts. Use a non-empty list
        to restrict the result to those statuses.

        ``knowledge_base_id=None`` means workspace-wide. Supplying it pushes the
        predicate into the store (UXA-408); callers must not read every row and
        filter in Python, which is what made a single KB's queue cost grow with
        every other KB's alert volume.
        """
        ...

    def get_alert(self, alert_id: str) -> AlertHistoryRecord | None:
        """Return one alert by id, or ``None`` when it does not exist."""
        ...

    def acknowledge(self, alert_id: str) -> AlertHistoryRecord | None:
        """Mark an alert acknowledged and return the updated record; ``None`` if unknown."""
        ...

    def assign(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str,
        assignee: str | None,
        actor: str,
    ) -> AlertHistoryRecord | None:
        """Assign an alert within a KB scope; ``None`` when the scoped alert is unknown."""
        ...

    def transition_status(
        self,
        alert_id: str,
        *,
        knowledge_base_id: str,
        status: str,
        actor: str,
        reason: str | None = None,
    ) -> AlertHistoryRecord | None:
        """Apply a valid lifecycle transition within a KB scope."""
        ...

    def count_by_statuses(self, statuses: set[str]) -> int:
        """Return how many alerts (across all knowledge bases) match one of ``statuses``."""
        ...

    def delete_by_kb(self, knowledge_base_id: str) -> int:
        """Delete all alert history for a knowledge base; return rows removed."""
        ...


@runtime_checkable
class AlertRepositoryProtocol(Protocol):
    """Persist and list alert read models for alert lifecycle operations."""

    def all(self) -> list[Alert]: ...

    def get(self, alert_id: str) -> Alert | None: ...

    def put(self, alert: Alert) -> None: ...


__all__ = [
    "AlertFeedStoreProtocol",
    "AlertHistoryWriter",
    "AlertRepositoryProtocol",
    "ObservationSourceProtocol",
    "ObservationWriter",
]
