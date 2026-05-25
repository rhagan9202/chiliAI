from __future__ import annotations

from pathlib import Path

from config.loader import load_config


def test_nppes_feed_is_declared_in_medicare_fraud_cms_desynpuf() -> None:
    config_path = Path(__file__).parents[2] / "config" / "defaults" / "medicare_fraud_cms_desynpuf.yaml"
    config = load_config(config_path)

    feed_names = {feed.name for feed in (config.records.feeds if config.records else [])}
    assert "nppes_providers" in feed_names

    provider = next(e for e in config.entities if e.name == "provider")
    assert "primary_taxonomy_code" in provider.properties
    assert "practice_state" in provider.properties
