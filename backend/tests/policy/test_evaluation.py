from __future__ import annotations

from config.schema import (
    PolicyCitationRef,
    PolicyPredicate,
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
)
from policy.evaluation import PolicyEvalState, evaluate
from shared.types import Entity


def _claim(entity_id: str, amount: float) -> Entity:
    return Entity(id=entity_id, type="claim", properties={"amount": amount})


def _pack() -> PolicyRulePack:
    return PolicyRulePack(
        id="billing",
        name="Billing thresholds",
        thresholds={"max_billed_amount": 1000.0},
        rules=[
            PolicyRule(
                id="claim_over_billed",
                title_template="Claim {target_ref} exceeds the billing threshold",
                severity="high",
                target_kind="entity",
                target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(
                    field="properties.amount",
                    op="gt",
                    value=PolicyPredicateValue(config_ref="max_billed_amount"),
                ),
                citations=[
                    PolicyCitationRef(
                        citation_id="c1", title="LCD", source_ref="policy://x"
                    )
                ],
            )
        ],
    )


def test_entity_predicate_emits_one_match_per_hit() -> None:
    state = PolicyEvalState(
        entities=[_claim("claim-1", 1500.0), _claim("claim-2", 500.0)], alerts=[], metrics={}
    )
    matches = evaluate([_pack()], state)
    assert len(matches) == 1
    match = matches[0]
    assert match.target_ref == "claim-1"
    assert match.rule_id == "claim_over_billed"
    assert match.title == "Claim claim-1 exceeds the billing threshold"
    assert match.matched_fields == {"properties.amount": 1500.0}
    assert match.citations[0].citation_id == "c1"


def test_metric_predicate_matches_metric_value() -> None:
    pack = PolicyRulePack(
        id="scale", name="scale", thresholds={"max_entities": 100.0},
        rules=[
            PolicyRule(
                id="kb_volume", title_template="KB {target_ref} large", severity="medium",
                target_kind="metric", target_selector={"metric_name": "entity_count"},
                predicate=PolicyPredicate(
                    field="metric.entity_count", op="gt",
                    value=PolicyPredicateValue(config_ref="max_entities"),
                ),
            )
        ],
    )
    state = PolicyEvalState(entities=[], alerts=[], metrics={"entity_count": 250.0})
    matches = evaluate([pack], state)
    assert len(matches) == 1
    assert matches[0].target_ref == "entity_count"


def test_in_operator_with_literal_list() -> None:
    pack = PolicyRulePack(
        id="states", name="states", thresholds={},
        rules=[
            PolicyRule(
                id="watch_states", title_template="Claim {target_ref} in watch state",
                severity="medium", target_kind="entity", target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(
                    field="properties.state", op="in",
                    value=PolicyPredicateValue(literal=["FL", "TX"]),
                ),
            )
        ],
    )
    state = PolicyEvalState(
        entities=[
            Entity(id="claim-1", type="claim", properties={"state": "FL"}),
            Entity(id="claim-2", type="claim", properties={"state": "CA"}),
        ], alerts=[], metrics={},
    )
    matches = evaluate([pack], state)
    assert [m.target_ref for m in matches] == ["claim-1"]


def test_no_match_when_field_absent() -> None:
    pack = _pack()
    state = PolicyEvalState(
        entities=[Entity(id="claim-3", type="claim", properties={})], alerts=[], metrics={}
    )
    assert evaluate([pack], state) == []
