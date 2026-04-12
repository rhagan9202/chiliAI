"""Event bus protocol for backend orchestration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from events.types import AnyEvent


@runtime_checkable
class EventBus(Protocol):
    """Publish and consume typed backend events."""

    def publish(self, event: AnyEvent) -> None: ...

    def consume(self, event_types: list[str], *, limit: int = 1) -> list[AnyEvent]: ...