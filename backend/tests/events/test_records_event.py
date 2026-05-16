"""Tests for the RecordsIngestedEvent type and its codec registration."""

from __future__ import annotations

from events.codec import EVENT_TYPE_REGISTRY, decode_event, encode_event
from events.types import RecordsIngestedEvent


def test_event_has_stable_type() -> None:
    event = RecordsIngestedEvent(
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        record_count=3,
    )
    assert event.event_type == "records.ingested"


def test_event_is_registered_in_codec() -> None:
    assert EVENT_TYPE_REGISTRY["records.ingested"] is RecordsIngestedEvent


def test_event_round_trips_through_the_codec() -> None:
    event = RecordsIngestedEvent(
        correlation_id="corr-1",
        knowledge_base_id="kb-1",
        feed_name="claims_feed",
        record_type="claim_record",
        record_count=5,
    )
    decoded = decode_event(encode_event(event))
    assert isinstance(decoded, RecordsIngestedEvent)
    assert decoded.correlation_id == "corr-1"
    assert decoded.knowledge_base_id == "kb-1"
    assert decoded.feed_name == "claims_feed"
    assert decoded.record_count == 5
