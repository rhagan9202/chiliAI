"""Test the peerstats worker stage helpers with in-memory adapters."""

from __future__ import annotations

from datetime import datetime, timezone

from analytics.peerstats.adapters.in_memory import (
    InMemoryDerivedRiskSignalWriter,
    InMemoryRecordColumnSource,
)
from analytics.peerstats.adapters.protocols import ColumnRow
from analytics.peerstats.service import create_peerstats_service
from agent.coordinator import run_peerstats_stage
from config.schema import PeerMetricSpec, PeerStatsConfig

MONDAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _spec(name: str) -> PeerMetricSpec:
    return PeerMetricSpec(
        name=name, record_type="claim_record", entity_type="provider",
        entity_id_field="provider_npi", value_column="billed_amount",
        aggregation="sum", interval="week", min_peers=2,
    )


def test_run_peerstats_stage_returns_deduped_affected_entities() -> None:
    source = InMemoryRecordColumnSource()
    source.add_rows("kb1", "claim_record", [
        ColumnRow(entity_id="provider:1", entity_type="provider",
                  group_values=(), value=10.0, observed_at=MONDAY),
        ColumnRow(entity_id="provider:2", entity_type="provider",
                  group_values=(), value=2.0, observed_at=MONDAY),
    ])
    writer = InMemoryDerivedRiskSignalWriter()
    service = create_peerstats_service(source, writer=writer)
    config = PeerStatsConfig(metrics=[_spec("m1"), _spec("m2")])

    affected = run_peerstats_stage(
        peerstats_service=service,
        peer_stats_config=config,
        knowledge_base_id="kb1",
        record_type="claim_record",
        correlation_id="c1",
    )
    # provider:1 and provider:2 each touched by two specs → deduped to two ids.
    assert affected == ["provider:1", "provider:2"]


def test_run_peerstats_stage_skips_nonmatching_record_type() -> None:
    source = InMemoryRecordColumnSource()
    writer = InMemoryDerivedRiskSignalWriter()
    service = create_peerstats_service(source, writer=writer)
    config = PeerStatsConfig(metrics=[_spec("m1")])
    affected = run_peerstats_stage(
        peerstats_service=service,
        peer_stats_config=config,
        knowledge_base_id="kb1",
        record_type="other_record",
        correlation_id="c1",
    )
    assert affected == []
