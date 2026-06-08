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
                      group_values=[], value=10.0, observed_at=monday),
            ColumnRow(entity_id="provider:1", entity_type="provider",
                      group_values=[], value=5.0, observed_at=wednesday),
            ColumnRow(entity_id="provider:2", entity_type="provider",
                      group_values=[], value=3.0, observed_at=monday),
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
