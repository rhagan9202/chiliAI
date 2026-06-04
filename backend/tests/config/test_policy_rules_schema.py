from __future__ import annotations

import pytest

from config.schema import (
    PolicyPredicate,
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
)


def test_predicate_value_requires_exactly_one_source() -> None:
    with pytest.raises(ValueError):
        PolicyPredicateValue()  # neither literal nor config_ref
    with pytest.raises(ValueError):
        PolicyPredicateValue(literal=1, config_ref="x")  # both
    assert PolicyPredicateValue(literal=1200).literal == 1200
    assert PolicyPredicateValue(config_ref="amt_threshold").config_ref == "amt_threshold"


def test_rule_pack_round_trips() -> None:
    pack = PolicyRulePack(
        id="billing",
        name="Billing thresholds",
        thresholds={"amt_threshold": 1000.0},
        rules=[
            PolicyRule(
                id="over_billed",
                title_template="Claim {target_ref} exceeds the billing threshold",
                severity="high",
                target_kind="entity",
                target_selector={"entity_type": "claim"},
                predicate=PolicyPredicate(
                    field="properties.billed_amount",
                    op="gt",
                    value=PolicyPredicateValue(config_ref="amt_threshold"),
                ),
            )
        ],
    )
    assert pack.rules[0].predicate.op == "gt"
    assert pack.thresholds["amt_threshold"] == 1000.0
