"""Tests for the in-memory risk adapter."""

from __future__ import annotations

from analytics.risk.adapters.in_memory import InMemoryRiskSignalSource
from analytics.risk.models import RiskProfile, RiskSignal


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