"""Guards the demo-tuned policy rule packs shipped in the default configs.

These assert that the rule packs in ``medicare_fraud_cms_desynpuf.yaml`` (the
config the dev stack loads) actually fire on representative ingested data, so a
plain ``make dev`` + ingest demonstrates live, worker-generated policy items.
A config edit that breaks the demo (renamed property, bad ``config_ref``,
mismatched target) fails here. See docs/adding_rulesets.md.
"""

from __future__ import annotations

from pathlib import Path

from config.loader import load_config
from policy.evaluation import PolicyEvalState, evaluate
from shared.types import Entity

_CMS_DESYNPUF = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "defaults"
    / "medicare_fraud_cms_desynpuf.yaml"
)


def test_cms_desynpuf_ships_rule_packs() -> None:
    cfg = load_config(_CMS_DESYNPUF)
    pack_ids = {pack.id for pack in cfg.policy_rules}
    assert {"elevated_payment_claims", "graph_scale_watch"} <= pack_ids


def test_elevated_payment_rule_fires_on_a_high_value_claim() -> None:
    cfg = load_config(_CMS_DESYNPUF)
    state = PolicyEvalState(
        entities=[
            Entity(id="CLM-9001", type="claim", properties={"amount": 600.0}),
            Entity(id="CLM-9002", type="claim", properties={"amount": 120.0}),
        ],
        alerts=[],
        metrics={},
    )
    matches = evaluate(cfg.policy_rules, state)
    fired = {(m.rule_id, m.target_ref) for m in matches}
    assert ("claim_elevated_payment", "CLM-9001") in fired
    assert ("claim_elevated_payment", "CLM-9002") not in fired  # below threshold


def test_entity_volume_rule_fires_once_the_graph_grows() -> None:
    cfg = load_config(_CMS_DESYNPUF)
    state = PolicyEvalState(entities=[], alerts=[], metrics={"entity_count": 100.0})
    matches = evaluate(cfg.policy_rules, state)
    assert any(m.rule_id == "kb_entity_volume" for m in matches)

    quiet = PolicyEvalState(entities=[], alerts=[], metrics={"entity_count": 10.0})
    assert not [m for m in evaluate(cfg.policy_rules, quiet) if m.rule_id == "kb_entity_volume"]
