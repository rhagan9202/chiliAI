from __future__ import annotations

from pathlib import Path

from config.loader import load_config


def test_inpatient_and_outpatient_feeds_load() -> None:
    config_path = Path(__file__).parents[2] / "config" / "defaults" / "medicare_fraud_cms_desynpuf.yaml"
    config = load_config(config_path)

    feed_names = {feed.name for feed in (config.records.feeds if config.records else [])}
    assert "inpatient_claims" in feed_names
    assert "outpatient_claims" in feed_names

    inpatient = next(f for f in config.records.feeds if f.name == "inpatient_claims")
    rel_types = {r.relationship_type for r in inpatient.relationships}
    assert rel_types == {"billed_for", "submitted_by", "performed_at"}

    outpatient = next(f for f in config.records.feeds if f.name == "outpatient_claims")
    assert {m.entity_type for m in outpatient.entities} == {"claim", "beneficiary", "provider", "facility"}
