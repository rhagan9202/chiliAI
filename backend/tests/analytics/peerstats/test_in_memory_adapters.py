"""Tests for in-memory peerstats adapters."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.models import DerivedRiskSignal
from config.schema import PeerMetricSpec


def _spec() -> PeerMetricSpec:
    return PeerMetricSpec(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
    )


def test_column_source_aggregates_per_entity_per_interval() -> None:
    source = InMemoryRecordColumnSource()
    monday = datetime(2026, 1, 5, tzinfo=timezone.utc)
    wednesday = datetime(2026, 1, 7, tzinfo=timezone.utc)
    source.add_rows(
        "kb1",
        "claim_record",
        [
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=(), value=10.0, observed_at=monday),
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=(), value=5.0, observed_at=wednesday),
            ColumnRow(entity_id="provider:2", entity_type="provider",
                      group_values=(), value=3.0, observed_at=monday),
        ],
    )
    aggregates = source.load_interval_aggregates(
        knowledge_base_id="kb1", spec=_spec(), interval_starts=[monday]
    )
    by_entity = {agg.entity_id: agg.aggregate_value for agg in aggregates}
    assert by_entity == {"provider:1": 15.0, "provider:2": 3.0}
    assert all(agg.peer_group_key == "provider" for agg in aggregates)


def test_writer_round_trips_signals() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    signal = DerivedRiskSignal(
        knowledge_base_id="kb1", entity_id="provider:1", entity_type="provider",
        metric_name="weekly_billing", interval_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        peer_group_key="provider", aggregate_value=15.0, peer_mean=9.0, peer_std=6.0,
        z_score=1.0, signal_value=0.25, weight=1.0, rationale="x", correlation_id="c1",
    )
    assert writer.write_signals([signal]) == 1
    latest = writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:1")
    assert latest[0].metric_name == "weekly_billing"
    assert latest[0].signal_value == 0.25
    assert latest[0].z_score == 1.0


def test_column_source_filters_out_of_range_intervals() -> None:
    source = InMemoryRecordColumnSource()
    week1 = datetime(2026, 1, 5, tzinfo=timezone.utc)  # Monday, week of Jan 5
    week2_obs = datetime(2026, 1, 14, tzinfo=timezone.utc)  # Wednesday of week of Jan 12
    source.add_rows(
        "kb1",
        "claim_record",
        [
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=(), value=10.0, observed_at=week1),
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=(), value=5.0, observed_at=week2_obs),
        ],
    )
    aggregates = source.load_interval_aggregates(
        knowledge_base_id="kb1", spec=_spec(), interval_starts=[week1]
    )
    assert len(aggregates) == 1
    assert aggregates[0].aggregate_value == 10.0  # week-2 row excluded by filter


def _signal(entity_id: str, *, knowledge_base_id: str = "kb1") -> DerivedRiskSignal:
    return DerivedRiskSignal(
        knowledge_base_id=knowledge_base_id, entity_id=entity_id,
        entity_type="provider", metric_name="weekly_billing",
        interval_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        peer_group_key="provider", aggregate_value=1.0, peer_mean=1.0,
        peer_std=0.0, z_score=0.0, signal_value=0.0, weight=1.0,
        rationale="r", correlation_id="c",
    )


def test_latest_signals_isolates_by_entity_and_kb() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    writer.write_signals(
        [
            _signal("provider:1"),
            _signal("provider:2"),
            _signal("provider:1", knowledge_base_id="kb2"),
        ]
    )
    assert len(writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:1")) == 1
    assert (
        writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:2")[0].entity_id
        == "provider:2"
    )
    assert len(writer.latest_signals(knowledge_base_id="kb2", entity_id="provider:1")) == 1
    assert writer.latest_signals(knowledge_base_id="kb1", entity_id="provider:99") == []
