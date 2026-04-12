"""Tests for the Redis Streams event bus adapter."""

from __future__ import annotations

from events.adapters.redis_streams import RedisStreamsEventBus
from events.types import DocumentReference, DocumentsUploadedEvent


class FakeRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.groups: set[tuple[str, str]] = set()
        self.acks: list[tuple[str, str, tuple[str, ...]]] = []

    def xadd(self, stream: str, fields: dict[str, str]) -> str:
        stream_messages = self.streams.setdefault(stream, [])
        message_id = f"{len(stream_messages) + 1}-0"
        stream_messages.append((message_id, fields))
        return message_id

    def xgroup_create(self, stream: str, groupname: str, id: str, mkstream: bool) -> bool:
        self.streams.setdefault(stream, [])
        key = (stream, groupname)
        if key in self.groups:
            raise Exception("BUSYGROUP Consumer Group name already exists")
        self.groups.add(key)
        return True

    def xreadgroup(
        self,
        *,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int,
        block: int | None,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        del consumername, block
        response: list[tuple[str, list[tuple[str, dict[str, str]]]]] = []
        for stream_name in streams:
            key = (stream_name, groupname)
            if key not in self.groups:
                continue
            messages = self.streams.get(stream_name, [])[:count]
            if messages:
                response.append((stream_name, messages))
        return response

    def xack(self, stream: str, groupname: str, *message_ids: str) -> int:
        self.acks.append((stream, groupname, message_ids))
        return len(message_ids)


def test_redis_streams_event_bus_publishes_consumes_and_acks() -> None:
    client = FakeRedis()
    event_bus = RedisStreamsEventBus(
        redis_url="redis://unused",
        stream_name_resolver=lambda event_type: f"chili.{event_type}",
        client=client,
    )
    event = DocumentsUploadedEvent(
        documents=[
            DocumentReference(
                knowledge_base_id="kb-1",
                source_document_id="doc-1",
            )
        ]
    )

    message_id = event_bus.publish(event)
    event_bus.ensure_consumer_group(["documents.uploaded"], consumer_group="workers")
    deliveries = event_bus.consume(
        ["documents.uploaded"],
        consumer_group="workers",
        consumer_name="worker-1",
    )
    event_bus.ack(deliveries)

    assert message_id == "1-0"
    assert len(deliveries) == 1
    assert deliveries[0].event == event
    assert client.acks == [("chili.documents.uploaded", "workers", ("1-0",))]