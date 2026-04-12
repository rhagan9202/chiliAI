"""Event bus contracts and event types."""

from events.adapters.in_memory import InMemoryEventBus
from events.protocols import EventBus
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
    "DocumentsFailedEvent",
    "DocumentsParsedEvent",
    "DocumentsUploadedEvent",
    "EventBase",
    "EventBus",
    "InMemoryEventBus",
    "KnowledgeBaseCreatedEvent",
    "ParsedDocumentReference",
]