"""Tests for the ConfigUpdatedEvent type and its codec registration (E6)."""

from __future__ import annotations

from events.codec import EVENT_TYPE_REGISTRY, decode_event, encode_event
from events.types import ConfigUpdatedEvent


def test_event_has_stable_type() -> None:
    event = ConfigUpdatedEvent(pack_name="food_supply")
    assert event.event_type == "config.updated"


def test_event_defaults() -> None:
    event = ConfigUpdatedEvent(pack_name="medicare_fraud")
    assert event.pack_path is None
    assert event.previous_pack_name is None
    assert event.reason == "apply"
    assert event.schema_version == 1
    assert event.correlation_id  # auto-generated envelope id


def test_event_is_registered_in_codec() -> None:
    assert EVENT_TYPE_REGISTRY["config.updated"] is ConfigUpdatedEvent


def test_event_round_trips_through_the_codec() -> None:
    event = ConfigUpdatedEvent(
        correlation_id="corr-config-1",
        source="api.config",
        pack_name="food_supply",
        pack_path="/packs/food_supply.yaml",
        previous_pack_name="medicare_fraud",
        reason="switch",
    )
    decoded = decode_event(encode_event(event))
    assert isinstance(decoded, ConfigUpdatedEvent)
    assert decoded.correlation_id == "corr-config-1"
    assert decoded.source == "api.config"
    assert decoded.pack_name == "food_supply"
    assert decoded.pack_path == "/packs/food_supply.yaml"
    assert decoded.previous_pack_name == "medicare_fraud"
    assert decoded.reason == "switch"
    assert decoded.occurred_at == event.occurred_at
