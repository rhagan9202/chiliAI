# Module: events

**Verified against codebase:** 2026-05-20
**Source:** `backend/events/`

## Purpose

Event bus abstraction. Decouples API from worker via Redis Streams (or in-memory for tests). Defines all typed event payloads that flow through the pipeline.

---

## Public Surface

### `events/protocols.py` — `EventBus` Protocol

```python
class EventBus(Protocol):
    def publish(self, event: AnyEvent) -> str | None: ...
    def ensure_consumer_group(self, event_types: list[str], *, consumer_group: str) -> None: ...
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
    def publish_to_dlq(self, event: AnyEvent, error_info: DlqErrorInfo) -> str | None: ...
```

### `events/types.py`

All typed event classes + `AnyEvent` union. See [contracts/events.md](../contracts/events.md) for full payload shapes.

### `events/codec.py`

Last verified: 2026-05-20

```python
EVENT_TYPE_REGISTRY: dict[str, type[EventBase]]
# Maps event_type string → EventBase subclass. Manually maintained.
# TODO in code: replace with auto-discovery via __init_subclass__ and add schema_version.

def encode_event(event: AnyEvent) -> dict[str, str]:
    """Serialize a typed event for Redis Streams transport.
    Returns {"event_type": str, "event_body": json_string}."""

def decode_event(payload: Mapping[str, str] | Mapping[bytes, bytes]) -> AnyEvent:
    """Deserialize from Redis Streams transport payload.
    Raises ValueError if event_type missing, unknown, or body event_type mismatch."""
```

Registered event types: `agent.workflow.started`, `alert.created`, `alerts.created`, `analysis.failed`, `pipeline.progress`, `kb.create`, `kb.delete`, `documents.uploaded`, `documents.parsed`, `documents.chunked`, `entities.extracted`, `entities.validated`, `graph.updated`, `embeddings.complete`, `vectors.indexed`, `kb.ready`, `llm.completed`, `embeddings.generated`, `rag.completed`, `timeseries.analyzed`, `gnn.analyzed`, `risk.scored`, `explainability.generated`, `documents.failed`, `claims.received`, `claims.ingested`, `records.ingested`.

### `events/runtime.py`

```python
# Factory: reads EventBusConfig from DomainConfig, returns appropriate adapter
```
Selects between `InMemoryEventBus` and `RedisStreamsEventBus`.

---

## Adapters

| Backend | File | Config |
|---------|------|--------|
| In-memory | `adapters/in_memory.py::InMemoryEventBus` | `EventBusConfig.backend = "in_memory"` |
| Redis Streams | `adapters/redis_streams.py` | `EventBusConfig.backend = "redis"` |

`InMemoryEventBus` is used in all tests and local/dev when Redis is unavailable.

---

## Module Dependencies

- `shared/types.py` — imports `Alert`
- `shared/utils.py` — imports `utc_now`, `generate_id`
- `pydantic` (for event models)

---

## Usage Pattern

```python
# API layer publishes
event_bus.publish(DocumentsUploadedEvent(documents=[...]))

# Worker consumes
deliveries = event_bus.consume(["documents.uploaded"], consumer_group="chili-workers", block_ms=1000)
for delivery in deliveries:
    # process delivery.event
    event_bus.ack([delivery])
```

Dead-letter queue: `publish_to_dlq()` captures failed events with `DlqErrorInfo` (error message, traceback, retry count).
