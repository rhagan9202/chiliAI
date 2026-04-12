"""In-memory event bus adapter for tests and local scaffolding."""

from __future__ import annotations

from events.types import AnyEvent


class InMemoryEventBus:
    """A process-local event bus with destructive consume semantics."""

    def __init__(self) -> None:
        self.published_events: list[AnyEvent] = []

    def publish(self, event: AnyEvent) -> None:
        self.published_events.append(event)

    def consume(self, event_types: list[str], *, limit: int = 1) -> list[AnyEvent]:
        matched: list[AnyEvent] = []
        remaining: list[AnyEvent] = []

        for event in self.published_events:
            if event.event_type in event_types and len(matched) < limit:
                matched.append(event)
            else:
                remaining.append(event)

        self.published_events = remaining
        return matched