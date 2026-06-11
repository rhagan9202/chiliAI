"""Service entry point for structured-record registration."""

from __future__ import annotations

from config.schema import RecordFeedConfig, RecordsConfig
from events.protocols import EventBus
from events.types import RecordsIngestedEvent
from records.adapters.protocols import RawRecordStore
from records.exceptions import RecordFeedNotFoundError, RecordValidationError
from records.models import (
    RawRecord,
    content_hash_for,
    submission_hash_for,
)
from records.service_models import RecordIngestReceipt, RecordSubmission
from records.validation import validate_rows_partition
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
        self,
        knowledge_base_id: str,
        submission: RecordSubmission,
        *,
        correlation_id: str | None = None,
    ) -> RecordIngestReceipt:
        feed = self._resolve_feed(submission.feed_name)
        coerced_rows, rejected = validate_rows_partition(feed, submission.rows)

        correlation_id = correlation_id or generate_id()
        ingested_at = utc_now()
        raw_records: list[RawRecord] = []
        for row in coerced_rows:
            if feed.id_template is not None:
                try:
                    record_id = feed.id_template.format(
                        **{k: str(v) for k, v in row.items()}
                    )
                except KeyError as exc:
                    raise RecordValidationError(
                        f"Feed '{feed.name}' id_template references missing field {exc}."
                    ) from exc
            else:
                raw_id = row.get(feed.id_field)
                if raw_id is None:
                    raise RecordValidationError(
                        f"Feed '{feed.name}' record is missing id field '{feed.id_field}'."
                    )
                record_id = str(raw_id)
            raw_records.append(
                RawRecord(
                    knowledge_base_id=knowledge_base_id,
                    record_type=feed.record_type,
                    record_id=record_id,
                    payload=row,
                    source_type=submission.source_type,
                    source_ref=submission.source_ref,
                    correlation_id=correlation_id,
                    content_hash=content_hash_for(row),
                    ingested_at=ingested_at,
                )
            )

        submission_hash = submission_hash_for(
            feed.name, [record.content_hash for record in raw_records]
        )
        if self._store.was_submitted(
            knowledge_base_id=knowledge_base_id, submission_hash=submission_hash
        ):
            # Identical batch already registered — no-op (no persist, no publish).
            return RecordIngestReceipt(
                knowledge_base_id=knowledge_base_id,
                feed_name=feed.name,
                record_type=feed.record_type,
                correlation_id=correlation_id,
                accepted_count=0,
                duplicate=True,
                duplicate_count=len(raw_records),
                rejected_count=len(rejected),
                rejected=rejected,
            )

        accepted = self._store.persist(raw_records)
        # Record the submission hash only after a successful persist, so a
        # persist failure does not poison the dedup set (a client retry must
        # not be falsely treated as a duplicate no-op).
        self._store.record_submission(
            knowledge_base_id=knowledge_base_id,
            submission_hash=submission_hash,
            correlation_id=correlation_id,
        )
        if accepted > 0:
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
            duplicate=False,
            rejected_count=len(rejected),
            rejected=rejected,
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
