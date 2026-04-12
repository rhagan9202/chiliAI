"""Tests for the in-memory event bus adapter."""

from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from events.types import DocumentReference, DocumentsUploadedEvent


def test_in_memory_event_bus_requires_ack_to_clear_delivery() -> None:
    event_bus = InMemoryEventBus()
    event_bus.publish(
        DocumentsUploadedEvent(
            documents=[
                DocumentReference(
                    knowledge_base_id="kb-1",
                    source_document_id="doc-1",
                )
            ]
        )
    )

    deliveries = event_bus.consume(
        ["documents.uploaded"],
        consumer_group="workers",
        consumer_name="worker-1",
    )

    assert len(deliveries) == 1
    assert deliveries[0].event.event_type == "documents.uploaded"

    second_read = event_bus.consume(
        ["documents.uploaded"],
        consumer_group="workers",
        consumer_name="worker-1",
    )
    assert second_read == []

    event_bus.ack(deliveries)

    third_read = event_bus.consume(
        ["documents.uploaded"],
        consumer_group="workers",
        consumer_name="worker-1",
    )
    assert third_read == []