"""Redis Streams event bus adapter."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable, Mapping
from typing import cast

from redis import Redis
from redis.exceptions import ResponseError

from events.codec import decode_event, encode_event
from events.dlq_models import DlqRecord
from events.protocols import DlqErrorInfo, DlqRecordStore, EventBus, EventDelivery
from events.types import AnyEvent
from shared.utils import generate_id, utc_now

__all__ = ["RedisStreamsEventBus"]

logger = logging.getLogger(__name__)

RedisValue = str | bytes
RedisPayload = Mapping[str, str] | Mapping[bytes, bytes]
RedisStreamMessage = tuple[RedisValue, RedisPayload]
RedisStreamResponse = list[tuple[RedisValue, list[RedisStreamMessage]]]
RedisAutoClaimResponse = tuple[RedisValue, list[RedisStreamMessage]] | tuple[
    RedisValue, list[RedisStreamMessage], list[RedisValue]
]


class RedisStreamsEventBus(EventBus):
    """Redis Streams-backed event bus implementation."""

    def __init__(
        self,
        *,
        redis_url: str,
        stream_name_resolver: Callable[[str], str],
        stream_maxlen: int | None = None,
        client: Redis | None = None,
        dlq_record_store: DlqRecordStore | None = None,
    ) -> None:
        self._client = client or Redis.from_url(redis_url)  # pyright: ignore[reportUnknownMemberType]
        self._stream_name_resolver = stream_name_resolver
        self._stream_maxlen = stream_maxlen
        # Undecodable messages are recorded here as well as on the Redis DLQ
        # stream, because `/events/dlq` reads the durable store — a message
        # that only reaches the stream is invisible to operators.
        self._dlq_record_store = dlq_record_store

    def publish(self, event: AnyEvent) -> str | None:
        # TODO(production): Add connection error handling with retry and backoff.
        stream = self._stream_name_resolver(event.event_type)
        message_id = cast(
            RedisValue,
            self._client.xadd(
                stream,
                encode_event(event),  # pyright: ignore[reportArgumentType]
                maxlen=self._stream_maxlen,
                approximate=self._stream_maxlen is not None,
            ),
        )
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
        response = cast(
            RedisStreamResponse,
            self._client.xreadgroup(
                groupname=consumer_group,
                consumername=consumer_name,
                streams=streams,  # pyright: ignore[reportArgumentType]
                count=limit,
                block=block_ms,
            ),
        )

        deliveries: list[EventDelivery] = []
        for stream_name, messages in response:
            decoded_stream = _decode_redis_string(stream_name)
            for message_id, payload in messages:
                decoded_id = _decode_redis_string(message_id)
                event = self._decode_or_quarantine(
                    payload,
                    message_id=decoded_id,
                    stream=decoded_stream,
                    consumer_group=consumer_group,
                )
                if event is None:
                    continue
                deliveries.append(
                    EventDelivery(
                        event=event,
                        event_id=decoded_id,
                        stream=decoded_stream,
                        consumer_group=consumer_group,
                    )
                )
        return deliveries

    def reclaim_stale_pending(
        self,
        event_types: list[str],
        *,
        consumer_group: str,
        consumer_name: str,
        min_idle_ms: int,
        limit: int = 10,
    ) -> list[EventDelivery]:
        deliveries: list[EventDelivery] = []
        for event_type in event_types:
            remaining = limit - len(deliveries)
            if remaining <= 0:
                break
            stream = self._stream_name_resolver(event_type)
            response = cast(
                RedisAutoClaimResponse,
                self._client.xautoclaim(
                    stream,
                    consumer_group,
                    consumer_name,
                    min_idle_ms,
                    "0-0",
                    count=remaining,
                ),
            )
            claimed_messages = response[1]
            for message_id, payload in claimed_messages:
                decoded_id = _decode_redis_string(message_id)
                event = self._decode_or_quarantine(
                    payload,
                    message_id=decoded_id,
                    stream=stream,
                    consumer_group=consumer_group,
                )
                if event is None:
                    continue
                deliveries.append(
                    EventDelivery(
                        event=event,
                        event_id=decoded_id,
                        stream=stream,
                        consumer_group=consumer_group,
                    )
                )
                if len(deliveries) >= limit:
                    break
        return deliveries

    def _decode_or_quarantine(
        self,
        payload: RedisPayload,
        *,
        message_id: str,
        stream: str,
        consumer_group: str,
    ) -> AnyEvent | None:
        """Decode one message, dead-lettering it rather than failing the batch.

        Decoding used to happen inline while building the delivery list, so a
        single unregistered ``event_type`` or a body that no longer validates
        took its whole ``XREADGROUP`` batch down with it: the exception escaped
        before the caller's retry/DLQ machinery, nothing in the batch was
        acked, and with no reclaim configured ``>`` never redelivers — so every
        good event that happened to share the batch was silently lost.

        An undecodable message cannot succeed on redelivery either, so it is
        dead-lettered and acked instead of being left pending forever where no
        operator surface would ever show it.
        """

        try:
            return decode_event(payload)
        except Exception as exc:  # noqa: BLE001 - every decode failure is dead-lettered
            self._quarantine_undecodable(
                payload,
                message_id=message_id,
                stream=stream,
                consumer_group=consumer_group,
                error=exc,
            )
            return None

    def _quarantine_undecodable(
        self,
        payload: RedisPayload,
        *,
        message_id: str,
        stream: str,
        consumer_group: str,
        error: BaseException,
    ) -> None:
        """Dead-letter and ack a message that could not be decoded."""

        normalized = {
            _decode_redis_string(key): _decode_redis_string(value)
            for key, value in payload.items()
        }
        error_message = f"{type(error).__name__}: {error}"
        error_traceback = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        failed_at = utc_now()
        logger.error(
            "Undecodable event dead-lettered. stream=%s message_id=%s error=%s",
            stream,
            message_id,
            error_message,
        )
        dlq_payload = dict(normalized)
        dlq_payload["error_message"] = error_message
        dlq_payload["error_traceback"] = error_traceback
        dlq_payload["retry_count"] = "0"
        dlq_payload["failed_at"] = failed_at.isoformat()
        self._client.xadd(f"{stream}.dlq", dlq_payload)  # pyright: ignore[reportArgumentType]
        if self._dlq_record_store is not None:
            try:
                self._dlq_record_store.persist(
                    DlqRecord(
                        dlq_id=generate_id(),
                        # An undecodable body may not carry either field; the
                        # transport event_type and message id are what an
                        # operator has to work with.
                        event_type=normalized.get("event_type", "unknown"),
                        correlation_id=normalized.get("correlation_id", message_id),
                        payload=normalized,
                        error_message=error_message,
                        error_traceback=error_traceback,
                        retry_count=0,
                        failed_at=failed_at,
                    )
                )
            except Exception:  # noqa: BLE001 - never lose the ack over bookkeeping
                logger.exception(
                    "Failed to persist durable DLQ record for an undecodable "
                    "event; the Redis DLQ entry still exists. stream=%s message_id=%s",
                    stream,
                    message_id,
                )
        self._client.xack(stream, consumer_group, message_id)

    def ack(self, deliveries: list[EventDelivery]) -> None:
        # Implement dead-letter routing for messages that fail N times.
        # Add graceful shutdown (stop consuming, finish in-flight, then exit).
        by_stream: dict[tuple[str, str], list[str]] = {}
        for delivery in deliveries:
            if delivery.stream is None or delivery.consumer_group is None or delivery.event_id is None:
                continue
            key = (delivery.stream, delivery.consumer_group)
            by_stream.setdefault(key, []).append(delivery.event_id)

        for (stream, consumer_group), event_ids in by_stream.items():
            self._client.xack(stream, consumer_group, *event_ids)

    def close(self) -> None:
        """Release the underlying Redis client's connection pool."""
        self._client.close()

    def publish_to_dlq(
        self,
        event: AnyEvent,
        error_info: DlqErrorInfo,
    ) -> str | None:
        """Publish a failed event into the dead-letter stream for the event type."""

        stream = self._stream_name_resolver(event.event_type)
        dlq_stream = f"{stream}.dlq"
        payload: dict[str, str] = dict(encode_event(event))
        payload["error_message"] = error_info.error_message
        payload["error_traceback"] = error_info.traceback
        payload["retry_count"] = str(error_info.retry_count)
        payload["failed_at"] = error_info.failed_at.isoformat()
        message_id = cast(
            RedisValue,
            self._client.xadd(dlq_stream, payload),  # pyright: ignore[reportArgumentType]
        )
        return _decode_redis_string(message_id)


def _decode_redis_string(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value
