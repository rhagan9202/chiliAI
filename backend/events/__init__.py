"""Event bus contracts and event types."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.adapters.redis_streams import RedisStreamsEventBus
from events.codec import decode_event, encode_event
from events.protocols import EventBus, EventDelivery
from events.runtime import EventBusSettings, create_event_bus, load_event_bus_settings
from events.types import (
    ChunkedDocumentReference,
    ClaimsIngestedEvent,
    ClaimsReceivedEvent,
    DocumentFailureReference,
    DocumentReference,
    EmbeddingGeneratedReference,
    EmbeddingsGeneratedEvent,
    EntitiesExtractedEvent,
    EntitiesValidatedEvent,
    ExtractedDocumentReference,
    GraphUpdatedDocumentReference,
    GraphUpdatedEvent,
    DocumentsChunkedEvent,
    DocumentsFailedEvent,
    DocumentsParsedEvent,
    DocumentsUploadedEvent,
    EventBase,
    KnowledgeBaseCreatedEvent,
    LlmCompletedEvent,
    LlmCompletionReference,
    ParsedDocumentReference,
    ValidatedDocumentReference,
    VectorIndexedReference,
    VectorsIndexedEvent,
)

__all__ = [
    "ChunkedDocumentReference",
    "ClaimsIngestedEvent",
    "ClaimsReceivedEvent",
    "DocumentFailureReference",
    "DocumentReference",
    "EmbeddingGeneratedReference",
    "EmbeddingsGeneratedEvent",
    "EntitiesExtractedEvent",
    "EntitiesValidatedEvent",
    "ExtractedDocumentReference",
    "GraphUpdatedDocumentReference",
    "GraphUpdatedEvent",
    "DocumentsChunkedEvent",
    "DocumentsFailedEvent",
    "DocumentsParsedEvent",
    "DocumentsUploadedEvent",
    "EventBus",
    "EventBusSettings",
    "EventDelivery",
    "EventBase",
    "InMemoryEventBus",
    "KnowledgeBaseCreatedEvent",
    "LlmCompletedEvent",
    "LlmCompletionReference",
    "ParsedDocumentReference",
    "ValidatedDocumentReference",
    "VectorIndexedReference",
    "VectorsIndexedEvent",
    "RedisStreamsEventBus",
    "create_event_bus",
    "decode_event",
    "encode_event",
    "load_event_bus_settings",
]