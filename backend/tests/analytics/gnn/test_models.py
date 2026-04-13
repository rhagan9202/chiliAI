"""Tests for gnn module models."""

from __future__ import annotations

import pytest

from analytics.gnn.models import GraphNodeSignal, GraphSnapshot


def test_graph_node_signal_requires_features() -> None:
    with pytest.raises(ValueError, match="at least one feature"):
        GraphNodeSignal(entity_id="provider-1", feature_values=[])


def test_graph_snapshot_requires_nodes() -> None:
    with pytest.raises(ValueError, match="at least one node"):
        GraphSnapshot(knowledge_base_id="kb-1", nodes=[])