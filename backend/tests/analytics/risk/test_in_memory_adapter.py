"""Tests for the in-memory risk adapter."""

from __future__ import annotations

import pytest

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RankedRiskEntry, RiskProfile, RiskSignal


def test_in_memory_signal_source_returns_seeded_profile() -> None:
    profile = RiskProfile(
        knowledge_base_id="kb-1",
        entity_id="provider-7",
        signals=[
            RiskSignal(signal_name="timeseries", value=0.7, weight=1.0),
            RiskSignal(signal_name="gnn_cluster", value=0.6, weight=1.0),
        ],
    )
    source = InMemoryRiskSignalSource(profiles=[profile])

    loaded = source.load_profile(knowledge_base_id="kb-1", entity_id="provider-7")

    assert loaded == profile


def test_in_memory_signal_source_raises_for_unknown_profile() -> None:
    source = InMemoryRiskSignalSource()

    with pytest.raises(ValueError, match="No risk profile registered"):
        source.load_profile(knowledge_base_id="kb-1", entity_id="missing")


def test_in_memory_signal_source_returns_ranked_entries_filtered_and_capped() -> None:
    source = InMemoryRiskSignalSource()
    source.put_ranked_entry(
        RankedRiskEntry(
            knowledge_base_id="kb-1",
            entity_id="a",
            entity_type="provider",
            overall_score=0.4,
            risk_level="low",
        )
    )
    source.put_ranked_entry(
        RankedRiskEntry(
            knowledge_base_id="kb-1",
            entity_id="b",
            entity_type="provider",
            overall_score=0.9,
            risk_level="high",
        )
    )
    source.put_ranked_entry(
        RankedRiskEntry(
            knowledge_base_id="kb-1",
            entity_id="c",
            entity_type="claim",
            overall_score=0.7,
            risk_level="medium",
        )
    )

    entries = source.list_ranked_entries(
        knowledge_base_id="kb-1",
        entity_type="provider",
        limit=1,
    )

    assert len(entries) == 1
    assert entries[0].entity_id == "b"