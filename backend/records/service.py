"""Service entry point for structured-record registration."""

from __future__ import annotations

from config.schema import RecordFeedConfig, RecordsConfig
from events.protocols import EventBus
from events.types import RecordsIngestedEvent
from records.adapters.protocols import RawRecordStore
from records.exceptions import RecordFeedNotFoundError
from records.models import (
    RawRecord,
    content_hash_for,
    submission_hash_for,
)
from records.service_models import RecordIngestReceipt, RecordSubmission
from records.validation import derive_record_id, validate_rows_partition
from shared.metrics import ingestion_dedup_suppressed_total
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
            # Raises RecordValidationError for a row with no derivable id,
            # failing the whole submission. That is deliberate for the upload
            # path — a client gets one clear error instead of a partial
            # ingest — so callers that must partition instead (the connector
            # executor) pre-filter with the same function.
            record_id = derive_record_id(feed, row)
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
            ingestion_dedup_suppressed_total.labels(kind="record_batch").inc()
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
            try:
                self._event_bus.publish(
                    RecordsIngestedEvent(
                        correlation_id=correlation_id,
                        knowledge_base_id=knowledge_base_id,
                        feed_name=feed.name,
                        record_type=feed.record_type,
                        record_count=accepted,
                    )
                )
            except Exception:
                # The rows are committed but no event references them, and
                # ``handle_records_ingested`` loads strictly by correlation id
                # — so nothing will ever read them. Leaving the submission
                # hash behind would compound that: the client's retry would
                # short-circuit to duplicate=True and publish nothing, and
                # re-persisting cannot help either because the rows already
                # exist under the *original* correlation id.
                #
                # Roll the whole attempt back instead, so the retry is a clean
                # first ingest. Only this attempt's rows are removed: rows that
                # pre-existed this submission carry a different correlation id.
                self._store.delete_batch(
                    knowledge_base_id=knowledge_base_id,
                    correlation_id=correlation_id,
                )
                self._store.discard_submission(
                    knowledge_base_id=knowledge_base_id,
                    submission_hash=submission_hash,
                )
                raise
        # Rows whose record_id already existed are silently dropped by the
        # store's per-row dedup during persist() (dedup behavior itself is
        # unchanged) — surface that so it isn't just "accepted came back
        # lower" with no visible cause.
        suppressed_existing = len(raw_records) - accepted
        if suppressed_existing > 0:
            ingestion_dedup_suppressed_total.labels(kind="record_row").inc(
                suppressed_existing
            )
        return RecordIngestReceipt(
            knowledge_base_id=knowledge_base_id,
            feed_name=feed.name,
            record_type=feed.record_type,
            correlation_id=correlation_id,
            accepted_count=accepted,
            duplicate=False,
            suppressed_existing_count=suppressed_existing,
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
