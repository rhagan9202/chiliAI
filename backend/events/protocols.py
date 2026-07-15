"""Event bus protocol for backend orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from events.dlq_models import DlqRecord, DlqRecordStatus
from events.types import AnyEvent
from shared.utils import utc_now


@dataclass(frozen=True, slots=True)
class EventDelivery:
    """A transport delivery containing a typed event and ack metadata."""

    event: AnyEvent
    event_id: str | None = None
    stream: str | None = None
    consumer_group: str | None = None


@dataclass(frozen=True, slots=True)
class DlqErrorInfo:
    """Structured failure context recorded alongside dead-lettered events."""

    error_message: str
    traceback: str
    retry_count: int
    failed_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class DlqEntry:
    """Captured dead-letter record with the original event and error context."""

    event: AnyEvent
    error: DlqErrorInfo
    stream: str | None = None


@runtime_checkable
class EventBus(Protocol):
    """Publish and consume typed backend events."""

    def publish(self, event: AnyEvent) -> str | None: ...

    def ensure_consumer_group(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
    ) -> None: ...

    def consume(
        self,
        event_types: list[str],
        *,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
        limit: int = 1,
        block_ms: int | None = None,
    ) -> list[EventDelivery]: ...

    def reclaim_stale_pending(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int,
        limit: int = 10,
    ) -> list[EventDelivery]: ...

    def ack(self, deliveries: list[EventDelivery]) -> None: ...

    def publish_to_dlq(
        self,
        event: AnyEvent,
        error_info: DlqErrorInfo,
    ) -> str | None: ...


@runtime_checkable
class DlqRecordStore(Protocol):
    """Durable operational ledger of dead-lettered events (BL-023)."""

    def persist(self, record: DlqRecord) -> DlqRecord:
        """Upsert ``record`` keyed on ``dlq_id``.

        Persisting the same ``dlq_id`` twice replaces the stored record with
        the latest one rather than erroring or creating a duplicate entry —
        the in-memory adapter overwrites the dict slot in place, and the
        Postgres adapter does the equivalent via
        ``INSERT ... ON CONFLICT (dlq_id) DO UPDATE SET`` over every non-PK
        column.
        """
        ...

    def list(
        self,
        *,
        status: DlqRecordStatus | None = None,
        event_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DlqRecord], int]: ...

    def get(self, dlq_id: str) -> DlqRecord | None: ...

    def mark_replayed(self, dlq_id: str) -> DlqRecord | None: ...

    def mark_discarded(self, dlq_id: str) -> DlqRecord | None: ...


__all__ = [
    "DlqEntry",
    "DlqErrorInfo",
    "DlqRecordStore",
    "EventBus",
    "EventDelivery",
]
