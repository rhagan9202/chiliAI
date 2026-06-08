"""Tests for peerstats domain models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from analytics.peerstats.models import DerivedRiskSignal, PeerAggregate


def _now() -> datetime:
    return datetime(2026, 1, 5, tzinfo=timezone.utc)


def test_peer_aggregate_fields() -> None:
    agg = PeerAggregate(
        entity_id="provider:1",
        entity_type="provider",
        peer_group_key="provider",
        interval_start=_now(),
        aggregate_value=12.5,
    )
    assert agg.aggregate_value == 12.5


def test_derived_signal_value_bounds() -> None:
    with pytest.raises(ValidationError):
        DerivedRiskSignal(
            knowledge_base_id="kb1",
            entity_id="provider:1",
            entity_type="provider",
            metric_name="weekly_billing",
            interval_start=_now(),
            peer_group_key="provider",
            aggregate_value=10.0,
            peer_mean=5.0,
            peer_std=2.0,
            z_score=2.5,
            signal_value=1.5,  # out of [0,1]
            weight=1.0,
            rationale="x",
            correlation_id="c1",
        )
