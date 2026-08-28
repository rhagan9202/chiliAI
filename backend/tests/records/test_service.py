"""Tests for RecordsService.register_records."""

from __future__ import annotations

from typing import cast

import pytest
from prometheus_client import REGISTRY

from config.schema import RecordEntityMapping, RecordFeedConfig, RecordsConfig
from events.adapters.in_memory import InMemoryEventBus
from events.types import RecordsIngestedEvent
from records.adapters.in_memory import InMemoryRawRecordStore
from records.exceptions import RecordFeedNotFoundError
from events.protocols import EventBus
from records.service import RecordsService, create_records_service
from records.service_models import RecordIngestReceipt
from records.service_models import RecordSubmission
from shared.types import PropertyDefinition, PropertyType


def _records_config() -> RecordsConfig:
    return RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="claims_feed",
                record_type="claim_record",
                source="file_upload",
                id_field="claim_id",
                record_schema={
                    "claim_id": PropertyDefinition(
                        type=PropertyType.STRING, display="Claim ID", required=True
                    ),
                    "amount": PropertyDefinition(
                        type=PropertyType.DECIMAL, display="Amount", required=True
                    ),
                },
                entities=[RecordEntityMapping(entity_type="claim", id_field="claim_id")],
            )
        ]
    )


def test_register_records_persists_publishes_and_receipts() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    receipt = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "10"}, {"claim_id": "c2", "amount": "20"}],
            source_type="file_upload",
            source_ref="claims.csv",
        ),
    )

    assert receipt.accepted_count == 2
    assert receipt.record_type == "claim_record"
    persisted = store.load_batch(
        knowledge_base_id="kb-1", correlation_id=receipt.correlation_id
    )
    assert {record.record_id for record in persisted} == {"c1", "c2"}
    assert persisted[0].payload["amount"] == 10.0  # coerced from "10"

    published = [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)]
    assert len(published) == 1
    assert published[0].correlation_id == receipt.correlation_id
    assert published[0].record_count == 2


def test_register_records_rejects_unknown_feed() -> None:
    service = create_records_service(
        InMemoryRawRecordStore(), event_bus=InMemoryEventBus(), records_config=_records_config()
    )
    with pytest.raises(RecordFeedNotFoundError):
        service.register_records(
            "kb-1",
            RecordSubmission(feed_name="ghost_feed", rows=[{}], source_type="api_push"),
        )


def test_register_records_does_not_publish_event_when_no_new_records() -> None:
    store = InMemoryRawRecordStore()
    event_bus = InMemoryEventBus()
    service = create_records_service(
        store,
        event_bus=event_bus,
        records_config=_records_config(),
    )
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[
            {
                "claim_id": "claim-1",
                "amount": "100",
            }
        ],
        source_type="api_push",
        source_ref=None,
    )

    first = service.register_records("kb-1", submission)
    second = service.register_records("kb-1", submission)

    assert first.accepted_count == 1
    assert second.accepted_count == 0
    assert [event.event_type for event in event_bus.published_events] == ["records.ingested"]


def test_register_records_uses_id_template() -> None:
    """When a feed declares id_template, record_id is the interpolated composite key."""
    config = RecordsConfig(
        feeds=[
            RecordFeedConfig(
                name="segmented_feed",
                record_type="seg_record",
                source="file_upload",
                id_field="CLM_ID",
                id_template="{CLM_ID}:{SEGMENT}",
                record_schema={
                    "CLM_ID": PropertyDefinition(
                        type=PropertyType.STRING, display="Claim ID", required=True
                    ),
                    "SEGMENT": PropertyDefinition(
                        type=PropertyType.STRING, display="Segment", required=True
                    ),
                },
            )
        ]
    )
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=config)
    receipt = service.register_records(
        "kb-seg",
        RecordSubmission(
            feed_name="segmented_feed",
            rows=[
                {"CLM_ID": "CLM001", "SEGMENT": "1"},
                {"CLM_ID": "CLM001", "SEGMENT": "2"},
            ],
            source_type="file_upload",
            source_ref="seg.csv",
        ),
    )
    assert receipt.accepted_count == 2
    persisted = store.load_batch(knowledge_base_id="kb-seg", correlation_id=receipt.correlation_id)
    record_ids = {r.record_id for r in persisted}
    assert record_ids == {"CLM001:1", "CLM001:2"}


def test_register_records_partitions_invalid_rows_without_raising() -> None:
    """A bad row is reported, not raised; valid rows still ingest (BL-015)."""
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    receipt = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[
                {"claim_id": "c1", "amount": "10"},
                {"claim_id": "c2"},  # missing required "amount"
            ],
            source_type="api_push",
        ),
    )

    assert receipt.accepted_count == 1
    assert receipt.rejected_count == 1
    assert [r.index for r in receipt.rejected] == [1]
    assert receipt.duplicate is False
    persisted = store.load_batch(
        knowledge_base_id="kb-1", correlation_id=receipt.correlation_id
    )
    assert {r.record_id for r in persisted} == {"c1"}


def test_register_records_all_rows_rejected_does_not_publish() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    receipt = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1"}],  # missing required "amount"
            source_type="api_push",
        ),
    )

    assert receipt.accepted_count == 0
    assert receipt.rejected_count == 1
    assert receipt.duplicate is False
    assert [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)] == []


def test_register_records_dedupes_identical_resubmission() -> None:
    """A re-pushed identical batch is a no-op flagged duplicate (BL-015)."""
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[{"claim_id": "c1", "amount": "10"}, {"claim_id": "c2", "amount": "20"}],
        source_type="api_push",
    )

    first = service.register_records("kb-1", submission)
    second = service.register_records("kb-1", submission)

    assert first.duplicate is False
    assert first.accepted_count == 2
    assert second.duplicate is True
    assert second.accepted_count == 0
    assert second.duplicate_count == 2
    # No second persistence and no second event.
    published = [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)]
    assert len(published) == 1


def test_register_records_dedup_is_row_order_independent() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    first = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "10"}, {"claim_id": "c2", "amount": "20"}],
            source_type="api_push",
        ),
    )
    # Same rows, reversed order → same submission hash → duplicate.
    second = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c2", "amount": "20"}, {"claim_id": "c1", "amount": "10"}],
            source_type="api_push",
        ),
    )

    assert first.duplicate is False
    assert second.duplicate is True
    assert second.accepted_count == 0


def test_register_records_duplicate_increments_dedup_counter() -> None:
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(
        store, event_bus=bus, records_config=_records_config()
    )
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=[{"claim_id": "c-dedup-1", "amount": "10"}],
        source_type="api_push",
    )
    labels = {"kind": "record_batch"}

    first = service.register_records("kb-dedup", submission)
    baseline = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    second = service.register_records("kb-dedup", submission)

    assert first.duplicate is False
    assert second.duplicate is True
    after = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    assert after == baseline + 1.0


def test_register_records_changed_row_resubmission_suppressed_not_duplicate() -> None:
    """A re-pushed row with the same record_id but CHANGED content is silently
    dropped by the per-row dedup in the store — that's existing, unchanged
    behavior. This test locks down that it now surfaces: accepted_count == 0,
    suppressed_existing_count == 1, and the batch is NOT flagged `duplicate`
    (the submission_hash differs because the content changed, so the
    batch-level no-op path is not taken; the row is just silently absorbed by
    persist())."""
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    first = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "10"}],
            source_type="api_push",
        ),
    )
    labels = {"kind": "record_row"}
    baseline = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0

    second = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "999"}],  # same record_id, changed content
            source_type="api_push",
        ),
    )

    assert first.accepted_count == 1
    assert second.accepted_count == 0
    assert second.suppressed_existing_count == 1
    assert second.duplicate is False
    after = REGISTRY.get_sample_value("ingestion_dedup_suppressed_total", labels) or 0.0
    assert after == baseline + 1.0


def test_register_records_mixed_batch_accepts_fresh_and_suppresses_changed_row() -> None:
    """A batch with one brand-new row and one changed re-push of an existing
    record_id accepts the new row and suppresses the stale one, both counted
    separately on the receipt."""
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(store, event_bus=bus, records_config=_records_config())

    first = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "c1", "amount": "10"}],
            source_type="api_push",
        ),
    )
    assert first.accepted_count == 1

    second = service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[
                {"claim_id": "c1", "amount": "999"},  # changed content, same id -> suppressed
                {"claim_id": "c2", "amount": "20"},  # fresh row -> accepted
            ],
            source_type="api_push",
        ),
    )

    assert second.accepted_count == 1
    assert second.suppressed_existing_count == 1
    assert second.duplicate is False


class _PublishFailsOnce:
    """Event bus that rejects the first publish and accepts the rest.

    Models Redis being briefly unavailable while the push endpoint is serving
    a batch — the rows are already committed by then.
    """

    def __init__(self) -> None:
        self.published_events: list[object] = []
        self._failed = False

    def publish(self, event: object) -> None:
        if not self._failed:
            self._failed = True
            raise RuntimeError("event bus unavailable")
        self.published_events.append(event)

    def subscribe(self, event_type: str, handler: object) -> None:
        return None


def _push(service: object, rows: list[dict[str, object]]) -> object:
    submission = RecordSubmission(
        feed_name="claims_feed",
        rows=rows,
        source_type="api_push",
        source_ref="push",
    )
    return cast(RecordsService, service).register_records("kb-1", submission)


def test_a_retry_after_a_failed_publish_still_reaches_the_pipeline() -> None:
    """A publish failure must not leave the persisted rows unreachable.

    The submission hash is what makes an identical retry a no-op. If it
    survives a failed publish, the retry short-circuits to duplicate=True and
    publishes nothing, while the rows it refers to sit in ``raw_records`` with
    a correlation id no event ever carried — the only consumer loads strictly
    by correlation id, so nothing ever maps them into the graph.
    """
    store = InMemoryRawRecordStore()
    bus = _PublishFailsOnce()
    service = create_records_service(
        store, event_bus=cast(EventBus, bus), records_config=_records_config()
    )
    rows: list[dict[str, object]] = [{"claim_id": "c1", "amount": "10"}]

    with pytest.raises(RuntimeError):
        _push(service, rows)

    receipt = cast(RecordIngestReceipt, _push(service, rows))

    assert receipt.duplicate is False
    published = [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)]
    assert len(published) == 1
    reachable = store.load_batch(
        knowledge_base_id="kb-1", correlation_id=published[0].correlation_id
    )
    assert {record.record_id for record in reachable} == {"c1"}


def test_a_successful_publish_still_dedupes_an_identical_retry() -> None:
    """The rollback must not weaken dedup on the happy path."""
    store = InMemoryRawRecordStore()
    bus = InMemoryEventBus()
    service = create_records_service(
        store, event_bus=bus, records_config=_records_config()
    )
    rows: list[dict[str, object]] = [{"claim_id": "c1", "amount": "10"}]

    _push(service, rows)
    second = cast(RecordIngestReceipt, _push(service, rows))

    assert second.duplicate is True
    assert second.accepted_count == 0
    published = [e for e in bus.published_events if isinstance(e, RecordsIngestedEvent)]
    assert len(published) == 1


class _PublishFailsOnNthCall:
    """Event bus that rejects one nominated publish and accepts the rest."""

    def __init__(self, *, fail_on_call: int) -> None:
        self.published_events: list[object] = []
        self._fail_on_call = fail_on_call
        self._calls = 0

    def publish(self, event: object) -> None:
        self._calls += 1
        if self._calls == self._fail_on_call:
            raise RuntimeError("event bus unavailable")
        self.published_events.append(event)

    def subscribe(self, event_type: str, handler: object) -> None:
        return None


def test_a_failed_page_does_not_delete_the_pages_already_published() -> None:
    """A connector sync run reuses one correlation id across every page.

    ``connectors/executor`` assigns the correlation id once per run and passes
    it to every ``register_records`` call, so a rollback keyed on the
    correlation id alone deletes the rows of every earlier page in the run —
    pages whose ``records.ingested`` events were already published and very
    likely already consumed.
    """
    store = InMemoryRawRecordStore()
    bus = _PublishFailsOnNthCall(fail_on_call=2)
    service = create_records_service(
        store, event_bus=cast(EventBus, bus), records_config=_records_config()
    )
    run_correlation_id = "corr-sync-run-1"

    service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "page1-a", "amount": "10"}],
            source_type="api_push",
            source_ref="connector:c1:run:r1",
        ),
        correlation_id=run_correlation_id,
    )
    with pytest.raises(RuntimeError):
        service.register_records(
            "kb-1",
            RecordSubmission(
                feed_name="claims_feed",
                rows=[{"claim_id": "page2-a", "amount": "20"}],
                source_type="api_push",
                source_ref="connector:c1:run:r1",
            ),
            correlation_id=run_correlation_id,
        )

    surviving = {
        record.record_id
        for record in store.load_batch(
            knowledge_base_id="kb-1", correlation_id=run_correlation_id
        )
    }
    assert surviving == {"page1-a"}, (
        "the failed page's rollback deleted rows from an already-published page: "
        f"{surviving}"
    )


def test_a_rollback_keeps_a_row_the_failed_call_did_not_insert() -> None:
    """persist() dedupes by record id, so a re-sent row is not this call's.

    A page that re-sends a record id an earlier page already landed inserts
    nothing for it. Rolling that row back would delete the earlier page's row,
    which is not this attempt's to remove.
    """
    store = InMemoryRawRecordStore()
    bus = _PublishFailsOnNthCall(fail_on_call=2)
    service = create_records_service(
        store, event_bus=cast(EventBus, bus), records_config=_records_config()
    )
    run_correlation_id = "corr-sync-run-2"

    service.register_records(
        "kb-1",
        RecordSubmission(
            feed_name="claims_feed",
            rows=[{"claim_id": "shared", "amount": "10"}],
            source_type="api_push",
        ),
        correlation_id=run_correlation_id,
    )
    with pytest.raises(RuntimeError):
        service.register_records(
            "kb-1",
            RecordSubmission(
                feed_name="claims_feed",
                rows=[
                    {"claim_id": "shared", "amount": "10"},
                    {"claim_id": "page2-only", "amount": "20"},
                ],
                source_type="api_push",
            ),
            correlation_id=run_correlation_id,
        )

    surviving = {
        record.record_id
        for record in store.load_batch(
            knowledge_base_id="kb-1", correlation_id=run_correlation_id
        )
    }
    assert surviving == {"shared"}
