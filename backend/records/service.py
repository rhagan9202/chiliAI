"""Service entry point for structured-record registration."""

from __future__ import annotations

from config.schema import RecordFeedConfig, RecordsConfig
from events.protocols import EventBus
from events.types import RecordsIngestedEvent
from records.adapters.protocols import RawRecordStore
from records.exceptions import RecordFeedNotFoundError, RecordValidationError
from records.models import RawRecord, content_hash_for
from records.service_models import RecordIngestReceipt, RecordSubmission
from records.validation import validate_rows
from shared.utils import generate_id, utc_now


class RecordsService:
    """Validate, persist, and announce structured-record submissions."""

    def __init__(
        self,
        store: RawRecordStore,
        *,
        event_bus: EventBus,
        records_config: RecordsConfig,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._records_config = records_config

    def register_records(
        self, knowledge_base_id: str, submission: RecordSubmission
    ) -> RecordIngestReceipt:
        feed = self._resolve_feed(submission.feed_name)
        coerced_rows = validate_rows(feed, submission.rows)

        correlation_id = generate_id()
        ingested_at = utc_now()
        raw_records: list[RawRecord] = []
        for row in coerced_rows:
            raw_id = row.get(feed.id_field)
            if raw_id is None:
                raise RecordValidationError(
                    f"Feed '{feed.name}' record is missing id field '{feed.id_field}'."
                )
            raw_records.append(
                RawRecord(
                    knowledge_base_id=knowledge_base_id,
                    record_type=feed.record_type,
                    record_id=str(raw_id),
                    payload=row,
                    source_type=submission.source_type,
                    source_ref=submission.source_ref,
                    correlation_id=correlation_id,
                    content_hash=content_hash_for(row),
                    ingested_at=ingested_at,
                )
            )

        accepted = self._store.persist(raw_records)
        self._event_bus.publish(
            RecordsIngestedEvent(
                correlation_id=correlation_id,
                knowledge_base_id=knowledge_base_id,
                feed_name=feed.name,
                record_type=feed.record_type,
                record_count=accepted,
            )
        )
        return RecordIngestReceipt(
            knowledge_base_id=knowledge_base_id,
            feed_name=feed.name,
            record_type=feed.record_type,
            correlation_id=correlation_id,
            accepted_count=accepted,
        )

    def _resolve_feed(self, feed_name: str) -> RecordFeedConfig:
        for feed in self._records_config.feeds:
            if feed.name == feed_name:
                return feed
        raise RecordFeedNotFoundError(feed_name)


def create_records_service(
    store: RawRecordStore,
    *,
    event_bus: EventBus,
    records_config: RecordsConfig,
) -> RecordsService:
    """Create the default records service."""

    return RecordsService(store, event_bus=event_bus, records_config=records_config)


__all__ = [
    "RecordsService",
    "create_records_service",
]
