"""Event bus contracts and event types."""

from events.adapters.redis_streams import RedisStreamsEventBus
from events.codec import decode_event, encode_event
from events.adapters.in_memory import InMemoryEventBus
from events.protocols import EventBus, EventDelivery
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from events.types import (
    ClaimsIngestedEvent,
    ClaimsReceivedEvent,
    DocumentFailureReference,
    DocumentReference,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EventBase,
    KnowledgeBaseCreatedEvent,
    ParsedDocumentReference,
)

__all__ = [
    "ClaimsIngestedEvent",
    "ClaimsReceivedEvent",
    "DocumentFailureReference",
    "DocumentReference",
    "EventBusSettings",
    "EventDelivery",
    "DocumentsFailedEvent",
    "DocumentsParsedEvent",
    "DocumentsUploadedEvent",
    "EventBase",
    "EventBus",
    "InMemoryEventBus",
    "KnowledgeBaseCreatedEvent",
    "ParsedDocumentReference",
    "RedisStreamsEventBus",
    "create_event_bus",
    "decode_event",
    "encode_event",
    "load_event_bus_settings",
]