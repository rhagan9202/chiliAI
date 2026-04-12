"""Event bus protocol for backend orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from events.types import AnyEvent


@dataclass(frozen=True, slots=True)
class EventDelivery:
    """A transport delivery containing a typed event and ack metadata."""

    event: AnyEvent
    event_id: str | None = None
    stream: str | None = None
    consumer_group: str | None = None


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

    def ack(self, deliveries: list[EventDelivery]) -> None: ...