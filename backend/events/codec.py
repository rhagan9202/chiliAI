"""Serialization helpers for typed backend events."""

from __future__ import annotations

import json
from collections.abc import Mapping

from events.types import (
    AnyEvent,
    ClaimsIngestedEvent,
    ClaimsReceivedEvent,
    EntitiesExtractedEvent,
    DocumentsChunkedEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EventBase,
    KnowledgeBaseCreatedEvent,
)


EVENT_TYPE_REGISTRY: dict[str, type[EventBase]] = {
    "kb.create": KnowledgeBaseCreatedEvent,
    "documents.uploaded": DocumentsUploadedEvent,
    "documents.parsed": DocumentsParsedEvent,
    "documents.chunked": DocumentsChunkedEvent,
    "entities.extracted": EntitiesExtractedEvent,
    "documents.failed": DocumentsFailedEvent,
    "claims.received": ClaimsReceivedEvent,
    "claims.ingested": ClaimsIngestedEvent,
}


def encode_event(event: AnyEvent) -> dict[str, str]:
    """Serialize a typed event for transport over Redis Streams."""
    return {
        "event_type": event.event_type,
        "event_body": event.model_dump_json(),
    }


def decode_event(payload: Mapping[str, str] | Mapping[bytes, bytes]) -> AnyEvent:
    """Deserialize a typed event from transport payload fields."""
    normalized = {_decode_key(key): _decode_value(value) for key, value in payload.items()}
    event_type = normalized.get("event_type")
    if event_type is None:
        raise ValueError("Event payload is missing 'event_type'.")

    event_body = normalized.get("event_body")
    if event_body is None:
        raise ValueError("Event payload is missing 'event_body'.")

    event_model = EVENT_TYPE_REGISTRY.get(event_type)
    if event_model is None:
        raise ValueError(f"Unsupported event type: {event_type}")
    return event_model.model_validate(json.loads(event_body))


def _decode_key(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _decode_value(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value