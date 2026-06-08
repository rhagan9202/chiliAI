"""Validation tests for peer-stats domain config."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import CapabilitiesConfig, PeerMetricSpec, PeerStatsConfig


def test_peer_metric_spec_defaults() -> None:
    spec = PeerMetricSpec(
        name="weekly_billing",
        record_type="claim_record",
        entity_type="provider",
        entity_id_field="provider_npi",
        value_column="billed_amount",
        aggregation="sum",
        interval="week",
    )
    assert spec.direction == "high"
    assert spec.z_cap == 4.0
    assert spec.weight == 1.0
    assert spec.min_peers == 5
    assert spec.group_by == []
    assert spec.time_column is None


def test_peer_metric_spec_rejects_nonpositive_z_cap() -> None:
    with pytest.raises(ValidationError):
        PeerMetricSpec(
            name="x",
            record_type="r",
            entity_type="e",
            entity_id_field="id",
            value_column="v",
            aggregation="mean",
            interval="day",
            z_cap=0.0,
        )


def test_peer_metric_spec_rejects_min_peers_below_two() -> None:
    with pytest.raises(ValidationError):
        PeerMetricSpec(
            name="x",
            record_type="r",
            entity_type="e",
            entity_id_field="id",
            value_column="v",
            aggregation="mean",
            interval="day",
            min_peers=1,
        )


def test_peer_stats_config_defaults_empty() -> None:
    assert PeerStatsConfig().metrics == []


def test_capabilities_peer_stats_defaults_false() -> None:
    assert CapabilitiesConfig().peer_stats is False
