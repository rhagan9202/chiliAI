"""Tests for config-driven seeded API state."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.state import create_api_state
from config.loader import load_config
from config.schema import DomainConfig

DEFAULTS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "defaults"


@pytest.mark.parametrize(
    "config_path",
    [
        DEFAULTS_DIR / "medicare_fraud.yaml",
        DEFAULTS_DIR / "food_supply_chain.yaml",
    ],
)
def test_seeded_state_uses_domain_config_for_graph_labels(
    config_path: Path,
) -> None:
    config: DomainConfig = load_config(config_path)
    state = create_api_state(config)

    graph_detail = state.get_graph_entity_detail("provider-204")

    assert graph_detail.entity.type == config.entities[0].name
    assert config.entities[0].display_label in graph_detail.entity.summary
