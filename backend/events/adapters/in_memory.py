"""In-memory event bus adapter for tests and local scaffolding."""

from __future__ import annotations

from dataclasses import dataclass

from events.protocols import EventDelivery
from events.types import AnyEvent

__all__ = ["InMemoryEventBus"]


@dataclass(slots=True)
class _QueuedEvent:
    event_id: str
    event: AnyEvent
    delivered: bool = False


class InMemoryEventBus:
    """A process-local event bus that mirrors the publish/consume/ack contract."""

    def __init__(self) -> None:
        self.published_events: list[AnyEvent] = []
        self._queue: list[_QueuedEvent] = []
        self._next_id = 1

    def publish(self, event: AnyEvent) -> str | None:
        event_id = str(self._next_id)
        self._next_id += 1
        self.published_events.append(event)
        self._queue.append(_QueuedEvent(event_id=event_id, event=event))
        return event_id

    def ensure_consumer_group(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
    ) -> None:
        # TODO(production): Track consumer groups and pending message state so the
        # in-memory adapter mirrors Redis Streams semantics for integration tests.
        return None

    def consume(
        self,
        event_types: list[str],
        *,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
        limit: int = 1,
        block_ms: int | None = None,
    ) -> list[EventDelivery]:
        matched: list[EventDelivery] = []
        for entry in self._queue:
            if entry.delivered:
                continue
            if entry.event.event_type not in event_types:
                continue
            entry.delivered = True
            matched.append(
                EventDelivery(
                    event=entry.event,
                    event_id=entry.event_id,
                    stream=entry.event.event_type,
                    consumer_group=consumer_group,
                )
            )
            if len(matched) >= limit:
                break
        return matched

    def ack(self, deliveries: list[EventDelivery]) -> None:
        acked_ids = {delivery.event_id for delivery in deliveries if delivery.event_id is not None}
        self._queue = [entry for entry in self._queue if entry.event_id not in acked_ids]