"""Tests for SAFE-CMS-011 peer-analysis workflow capability integration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

import analytics.peerstats as peerstats
from analytics.peerstats.adapters.in_memory import InMemoryDerivedRiskSignalWriter
from analytics.peerstats.capability import (
    PeerAnalysisCapabilityDisabledError,
    create_peer_analysis_capability_registry,
)
from analytics.peerstats.models import DerivedRiskSignal
from analytics.peerstats.peer_analysis import PeerAnalysisResponse, PeerAnalysisService
from config.schema import CapabilitiesConfig


def _signal(
    entity_id: str,
    *,
    value: float,
    interval_start: datetime,
    metric_name: str = "weekly_billing",
) -> DerivedRiskSignal:
    return DerivedRiskSignal(
        knowledge_base_id="kb1",
        entity_id=entity_id,
        entity_type="facility",
        metric_name=metric_name,
        interval_start=interval_start,
        peer_group_key="facility|region-a",
        aggregate_value=value,
        peer_mean=50.0,
        peer_std=20.0,
        z_score=(value - 50.0) / 20.0,
        signal_value=min(max(value / 100.0, 0.0), 1.0),
        weight=1.0,
        rationale="weekly billing compared to peer facilities",
        correlation_id="corr-1",
    )


def test_peer_analysis_capability_registry_executes_kb_scoped_peer_analysis() -> None:
    writer = InMemoryDerivedRiskSignalWriter()
    interval = datetime(2026, 1, 12, tzinfo=timezone.utc)
    writer.write_signals(
        [
            _signal("facility:target", value=90.0, interval_start=interval),
            _signal("facility:peer", value=30.0, interval_start=interval),
            _signal(
                "facility:target",
                value=4.0,
                interval_start=interval,
                metric_name="daily_claim_count",
            ),
        ]
    )
    registry = create_peer_analysis_capability_registry(
        PeerAnalysisService(writer, min_cohort_size=2)
    )

    descriptor = registry.get("analytics.peer_context")
    result = registry.execute(
        "analytics.peer_context",
        {
            "knowledge_base_id": "kb1",
            "entity_id": "facility:target",
            "metric_name": "weekly_billing",
        },
        capabilities=CapabilitiesConfig(peer_stats=True),
    )

    assert descriptor.required_capability == "peer_stats"
    assert isinstance(result, PeerAnalysisResponse)
    assert result.knowledge_base_id == "kb1"
    assert result.entity_id == "facility:target"
    assert [metric.metric_name for metric in result.metrics] == ["weekly_billing"]


def test_peer_analysis_capability_rejects_disabled_peer_stats() -> None:
    registry = create_peer_analysis_capability_registry(
        PeerAnalysisService(InMemoryDerivedRiskSignalWriter())
    )

    with pytest.raises(PeerAnalysisCapabilityDisabledError, match="peer_stats"):
        registry.execute(
            "analytics.peer_context",
            {"knowledge_base_id": "kb1", "entity_id": "facility:target"},
            capabilities=CapabilitiesConfig(peer_stats=False),
        )


def test_peerstats_package_exports_peer_analysis_capability_factory() -> None:
    assert (
        getattr(peerstats, "create_peer_analysis_capability_registry")
        is create_peer_analysis_capability_registry
    )


def test_the_adapter_uses_the_published_capability_id() -> None:
    """The manifest id is the contract; the adapter id is an implementation detail.

    They were `analytics.peer_context` (manifest, with no implementation) and
    `analytics.peer_analysis` (adapter, which no manifest declared) — two halves
    of one feature under different names, so neither was reachable. The adapter
    is what moves: workflow definitions reference the manifest id and the browse
    API returns it.
    """
    from typing import get_args

    from analytics.peerstats.capability import PeerAnalysisCapabilityId

    assert get_args(PeerAnalysisCapabilityId) == ("analytics.peer_context",)


def test_the_published_id_is_a_registered_manifest() -> None:
    from capabilities.service import create_default_capability_registry_service

    registered = {
        manifest.capability_id
        for manifest in create_default_capability_registry_service()
        .list_capabilities()
        .items
    }

    assert "analytics.peer_context" in registered
