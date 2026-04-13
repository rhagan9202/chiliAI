"""Redis Streams event bus adapter."""

from __future__ import annotations

from collections.abc import Callable

from redis import Redis
from redis.exceptions import ResponseError

from events.codec import decode_event, encode_event
from events.protocols import EventBus, EventDelivery
from events.types import AnyEvent

__all__ = ["RedisStreamsEventBus"]


class RedisStreamsEventBus(EventBus):
    """Redis Streams-backed event bus implementation."""

    def __init__(
        self,
        *,
        redis_url: str,
        stream_name_resolver: Callable[[str], str],
        client: Redis | None = None,
    ) -> None:
        self._client = client or Redis.from_url(redis_url)
        self._stream_name_resolver = stream_name_resolver

    def publish(self, event: AnyEvent) -> str | None:
        stream = self._stream_name_resolver(event.event_type)
        message_id = self._client.xadd(stream, encode_event(event))
        return _decode_redis_string(message_id)

    def ensure_consumer_group(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
    ) -> None:
        for event_type in event_types:
            stream = self._stream_name_resolver(event_type)
            try:
                self._client.xgroup_create(stream, consumer_group, id="0", mkstream=True)
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    def consume(
        self,
        event_types: list[str],
        *,
        consumer_group: str | None = None,
        consumer_name: str | None = None,
        limit: int = 1,
        block_ms: int | None = None,
    ) -> list[EventDelivery]:
        if consumer_group is None or consumer_name is None:
            raise ValueError("Redis Streams consumption requires a consumer group and consumer name.")

        streams = {self._stream_name_resolver(event_type): ">" for event_type in event_types}
        response = self._client.xreadgroup(
            groupname=consumer_group,
            consumername=consumer_name,
            streams=streams,
            count=limit,
            block=block_ms,
        )

        deliveries: list[EventDelivery] = []
        for stream_name, messages in response:
            decoded_stream = _decode_redis_string(stream_name)
            for message_id, payload in messages:
                deliveries.append(
                    EventDelivery(
                        event=decode_event(payload),
                        event_id=_decode_redis_string(message_id),
                        stream=decoded_stream,
                        consumer_group=consumer_group,
                    )
                )
        return deliveries

    def ack(self, deliveries: list[EventDelivery]) -> None:
        by_stream: dict[tuple[str, str], list[str]] = {}
        for delivery in deliveries:
            if delivery.stream is None or delivery.consumer_group is None or delivery.event_id is None:
                continue
            key = (delivery.stream, delivery.consumer_group)
            by_stream.setdefault(key, []).append(delivery.event_id)

        for (stream, consumer_group), event_ids in by_stream.items():
            self._client.xack(stream, consumer_group, *event_ids)


def _decode_redis_string(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value