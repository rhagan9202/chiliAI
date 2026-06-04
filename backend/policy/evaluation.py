"""Pure evaluation of configured policy rule packs against KB state.

No I/O: ``evaluate(rule_packs, state) -> list[PolicyMatch]``. The worker calls
this with freshly-stored entities and (throttled) graph metrics; the result is
upserted as durable policy items.
"""

from __future__ import annotations

from collections import defaultdict
from typing import cast

from pydantic import BaseModel, Field

from config.schema import (
    PolicyPredicateValue,
    PolicyRule,
    PolicyRulePack,
)
from policy.models import MatchedValue, PolicyCitation, PolicySeverity, PolicyTargetKind
from shared.types import Alert, Entity

__all__ = ["PolicyEvalState", "PolicyMatch", "evaluate"]


class PolicyEvalState(BaseModel):
    """The KB-scoped state a rule pack is evaluated against."""

    entities: list[Entity] = Field(default_factory=lambda: cast(list[Entity], []))
    alerts: list[Alert] = Field(default_factory=lambda: cast(list[Alert], []))
    metrics: dict[str, float] = Field(default_factory=lambda: cast(dict[str, float], {}))


class PolicyMatch(BaseModel):
    """A single rule hit, ready to be upserted as a ``PolicyItem``."""

    rule_id: str
    rule_pack_id: str
    target_kind: PolicyTargetKind
    target_ref: str
    title: str
    severity: PolicySeverity
    matched_fields: dict[str, MatchedValue]
    citations: list[PolicyCitation]


def evaluate(rule_packs: list[PolicyRulePack], state: PolicyEvalState) -> list[PolicyMatch]:
    matches: list[PolicyMatch] = []
    for pack in rule_packs:
        for rule in pack.rules:
            matches.extend(_evaluate_rule(pack, rule, state))
    return matches


def _evaluate_rule(
    pack: PolicyRulePack, rule: PolicyRule, state: PolicyEvalState
) -> list[PolicyMatch]:
    resolved = _resolve_value(pack, rule.predicate.value)
    out: list[PolicyMatch] = []
    for target_ref, field_value in _iter_targets(rule, state):
        if field_value is None:
            continue
        if _apply(rule.predicate.op, field_value, resolved):
            out.append(
                PolicyMatch(
                    rule_id=rule.id,
                    rule_pack_id=pack.id,
                    target_kind=rule.target_kind,
                    target_ref=target_ref,
                    title=_render_title(rule.title_template, target_ref),
                    severity=rule.severity,
                    matched_fields={rule.predicate.field: _as_matched(field_value)},
                    citations=[
                        PolicyCitation(
                            citation_id=c.citation_id,
                            title=c.title,
                            source_ref=c.source_ref,
                            excerpt=c.excerpt,
                        )
                        for c in rule.citations
                    ],
                )
            )
    return out


def _iter_targets(
    rule: PolicyRule, state: PolicyEvalState
) -> list[tuple[str, object | None]]:
    """Yield ``(target_ref, field_value)`` pairs for a rule's selected targets."""

    if rule.target_kind == "entity":
        wanted = rule.target_selector.get("entity_type")
        return [
            (entity.id, _entity_field(entity, rule.predicate.field))
            for entity in state.entities
            if wanted is None or entity.type == wanted
        ]
    if rule.target_kind == "metric":
        name = rule.target_selector.get("metric_name", "")
        if name not in state.metrics:
            return []
        return [(name, state.metrics[name])]
    # target_kind == "alert": defined but not evaluated in v1 (documented non-goal).
    return []


def _entity_field(entity: Entity, field: str) -> object | None:
    if field.startswith("properties."):
        return entity.properties.get(field.split(".", 1)[1])
    if field == "risk_score":
        return entity.properties.get("risk_score")
    return None


def _resolve_value(pack: PolicyRulePack, value: PolicyPredicateValue) -> object:
    if value.config_ref is not None:
        return pack.thresholds[value.config_ref]
    return value.literal


def _apply(op: str, left: object, right: object) -> bool:
    if op == "in":
        return left in _as_list(right)
    if op == "not_in":
        return left not in _as_list(right)
    if op == "eq":
        return left == right
    if op == "neq":
        return left != right
    left_n, right_n = _as_float(left), _as_float(right)
    if left_n is None or right_n is None:
        return False
    if op == "gt":
        return left_n > right_n
    if op == "gte":
        return left_n >= right_n
    if op == "lt":
        return left_n < right_n
    if op == "lte":
        return left_n <= right_n
    return False


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    if isinstance(value, tuple):
        return list(cast(tuple[object, ...], value))
    return [value]


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_matched(value: object) -> MatchedValue:
    if isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _render_title(template: str, target_ref: str) -> str:
    safe: defaultdict[str, str] = defaultdict(str)
    safe["target_ref"] = target_ref
    return template.format_map(safe)
