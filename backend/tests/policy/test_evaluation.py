from __future__ import annotations

import pytest

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


def _entity_rule(*, op: str, value: PolicyPredicateValue, field: str = "properties.amount") -> PolicyRulePack:
    return PolicyRulePack(
        id="pack",
        name="pack",
        thresholds={},
        rules=[
            PolicyRule(
                id="r",
                title_template="Claim {target_ref}",
                severity="medium",
                target_kind="entity",
                target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(field=field, op=op, value=value),  # type: ignore[arg-type]
            )
        ],
    )


@pytest.mark.parametrize(
    ("op", "literal", "amount", "expect_match"),
    [
        ("eq", 100.0, 100.0, True),
        ("eq", 100.0, 101.0, False),
        ("neq", 100.0, 101.0, True),
        ("neq", 100.0, 100.0, False),
        ("gt", 100.0, 150.0, True),
        ("gt", 100.0, 100.0, False),
        ("gte", 100.0, 100.0, True),
        ("gte", 100.0, 99.0, False),
        ("lt", 100.0, 99.0, True),
        ("lt", 100.0, 100.0, False),
        ("lte", 100.0, 100.0, True),
        ("lte", 100.0, 101.0, False),
    ],
)
def test_numeric_and_equality_operators(
    op: str, literal: float, amount: float, expect_match: bool
) -> None:
    pack = _entity_rule(op=op, value=PolicyPredicateValue(literal=literal))
    state = PolicyEvalState(entities=[_claim("claim-1", amount)], alerts=[], metrics={})
    matches = evaluate([pack], state)
    assert bool(matches) is expect_match


def test_not_in_operator() -> None:
    pack = _entity_rule(
        op="not_in", value=PolicyPredicateValue(literal=["FL", "TX"]), field="properties.state"
    )
    state = PolicyEvalState(
        entities=[
            Entity(id="claim-1", type="claim", properties={"state": "CA"}),
            Entity(id="claim-2", type="claim", properties={"state": "FL"}),
        ],
        alerts=[],
        metrics={},
    )
    assert [m.target_ref for m in evaluate([pack], state)] == ["claim-1"]


def test_numeric_operator_with_non_numeric_value_does_not_match() -> None:
    # left side is a non-numeric string -> _as_float returns None -> no match.
    pack = _entity_rule(op="gt", value=PolicyPredicateValue(literal=100.0), field="properties.note")
    state = PolicyEvalState(
        entities=[Entity(id="claim-1", type="claim", properties={"note": "n/a"})],
        alerts=[],
        metrics={},
    )
    assert evaluate([pack], state) == []


def test_numeric_operator_coerces_string_amount() -> None:
    pack = _entity_rule(op="gt", value=PolicyPredicateValue(literal=100.0))
    state = PolicyEvalState(
        entities=[Entity(id="claim-1", type="claim", properties={"amount": "150"})],
        alerts=[],
        metrics={},
    )
    assert len(evaluate([pack], state)) == 1


def test_risk_score_field_resolution() -> None:
    pack = _entity_rule(op="gte", value=PolicyPredicateValue(literal=0.8), field="risk_score")
    state = PolicyEvalState(
        entities=[Entity(id="claim-1", type="claim", properties={"risk_score": 0.9})],
        alerts=[],
        metrics={},
    )
    assert len(evaluate([pack], state)) == 1


def test_unknown_entity_field_yields_no_match() -> None:
    pack = _entity_rule(op="gt", value=PolicyPredicateValue(literal=1.0), field="nope")
    state = PolicyEvalState(entities=[_claim("claim-1", 9.0)], alerts=[], metrics={})
    assert evaluate([pack], state) == []


def test_alert_target_is_not_evaluated_in_v1() -> None:
    pack = PolicyRulePack(
        id="pack",
        name="pack",
        thresholds={},
        rules=[
            PolicyRule(
                id="r",
                title_template="t",
                severity="high",
                target_kind="alert",
                target_selector={},
                predicate=PolicyPredicate(
                    field="risk_score", op="gt", value=PolicyPredicateValue(literal=0.1)
                ),
            )
        ],
    )
    state = PolicyEvalState(entities=[], alerts=[], metrics={})
    assert evaluate([pack], state) == []


def test_metric_target_absent_metric_yields_no_match() -> None:
    pack = PolicyRulePack(
        id="pack",
        name="pack",
        thresholds={},
        rules=[
            PolicyRule(
                id="r",
                title_template="{target_ref}",
                severity="medium",
                target_kind="metric",
                target_selector={"metric_name": "missing"},
                predicate=PolicyPredicate(
                    field="metric.missing", op="gt", value=PolicyPredicateValue(literal=1.0)
                ),
            )
        ],
    )
    state = PolicyEvalState(entities=[], alerts=[], metrics={"entity_count": 5.0})
    assert evaluate([pack], state) == []
