"""Runtime configuration and factory helpers for event transport."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from events.adapters.in_memory import InMemoryEventBus
from events.adapters.redis_streams import RedisStreamsEventBus
from events.protocols import EventBus


@dataclass(frozen=True, slots=True)
class EventBusSettings:
    """Runtime settings for event transport selection and Redis Streams."""

    backend: str = "in-memory"
    redis_url: str = "redis://localhost:6379/0"
    stream_prefix: str = "chili"
    consumer_group: str = "chili-workers"
    consumer_name_prefix: str = "worker"
    batch_size: int = 10
    block_ms: int = 1000

    def consumer_name(self) -> str:
        """Return a unique consumer identifier for the running process."""
        return f"{self.consumer_name_prefix}-{socket.gethostname()}-{os.getpid()}"

    def stream_name(self, event_type: str) -> str:
        """Return the Redis stream name for an event type."""
        return f"{self.stream_prefix}.{event_type}" if self.stream_prefix else event_type


def load_event_bus_settings() -> EventBusSettings:
    """Load event bus settings from environment variables."""
    return EventBusSettings(
        backend=os.environ.get("CHILI_EVENT_BUS_BACKEND", "in-memory"),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        stream_prefix=os.environ.get("CHILI_EVENT_STREAM_PREFIX", "chili"),
        consumer_group=os.environ.get("CHILI_EVENT_CONSUMER_GROUP", "chili-workers"),
        consumer_name_prefix=os.environ.get("CHILI_EVENT_CONSUMER_NAME_PREFIX", "worker"),
        batch_size=int(os.environ.get("CHILI_EVENT_BATCH_SIZE", "10")),
        block_ms=int(os.environ.get("CHILI_EVENT_BLOCK_MS", "1000")),
    )


def create_event_bus(settings: EventBusSettings | None = None) -> EventBus:
    """Create an event bus adapter for the configured runtime."""
    # TODO(production): Wire event bus settings from DomainConfig YAML instead of
    # env-only. Add connection health check (PING) on startup. Support TLS/auth
    # for Redis connections (rediss:// URIs, password, client certs). Add connection
    # pool configuration (max_connections, socket_timeout, retry_on_timeout).
    resolved = settings or load_event_bus_settings()
    if resolved.backend == "redis":
        return RedisStreamsEventBus(
            redis_url=resolved.redis_url,
            stream_name_resolver=resolved.stream_name,
        )
    return InMemoryEventBus()


__all__ = [
    "EventBusSettings",
    "create_event_bus",
    "load_event_bus_settings",
]