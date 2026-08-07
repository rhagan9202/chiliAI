"""Tests for the restricted workflow condition grammar.

A workflow `condition` is user-authored content in a multi-tenant system.
`eval` on it is remote code execution, so the grammar is deliberately tiny and
everything outside it is a syntax error rather than a best-effort parse.

The hostile-input parametrisation is the substance of this file: each entry is
a payload that would do real damage if any evaluation path existed.
"""

from __future__ import annotations

import re

import pytest

from workflow_definitions.models import (
    WorkflowDefinitionCreate,
    WorkflowStepDefinition,
    validate_workflow_definition_payload,
)
from workflow_definitions.conditions import (
    ConditionSyntaxError,
    evaluate_condition,
    parse_condition,
)


# --- the grammar ------------------------------------------------------------


def test_evaluates_a_simple_string_comparison() -> None:
    assert (
        evaluate_condition(
            "enrich.risk_level == 'high'",
            outputs={"enrich": {"risk_level": "high"}},
        )
        is True
    )


def test_a_false_comparison_is_false() -> None:
    assert (
        evaluate_condition(
            "enrich.risk_level == 'high'",
            outputs={"enrich": {"risk_level": "low"}},
        )
        is False
    )


@pytest.mark.parametrize(
    ("condition", "value", "expected"),
    [
        ("s.n != 3", 4, True),
        ("s.n != 3", 3, False),
        ("s.n > 3", 4, True),
        ("s.n > 3", 3, False),
        ("s.n >= 3", 3, True),
        ("s.n < 3", 2, True),
        ("s.n <= 3", 3, True),
        ("s.n <= 3", 4, False),
    ],
)
def test_supports_every_comparison_operator(
    condition: str, value: object, expected: bool
) -> None:
    assert evaluate_condition(condition, outputs={"s": {"n": value}}) is expected


@pytest.mark.parametrize(
    ("literal", "value", "expected"),
    [
        ("'high'", "high", True),
        ('"high"', "high", True),
        ("3", 3, True),
        ("3.5", 3.5, True),
        ("-2", -2, True),
        ("true", True, True),
        ("false", False, True),
        ("null", None, True),
    ],
)
def test_supports_every_literal_form(
    literal: str, value: object, expected: bool
) -> None:
    assert (
        evaluate_condition(f"s.k == {literal}", outputs={"s": {"k": value}}) is expected
    )


def test_tolerates_surrounding_whitespace() -> None:
    assert (
        evaluate_condition(
            "  enrich.risk_level   ==   'high'  ",
            outputs={"enrich": {"risk_level": "high"}},
        )
        is True
    )


# --- missing data is False, not an error ------------------------------------


def test_missing_step_output_is_false_not_an_error() -> None:
    """A step that was skipped has no outputs; that is a normal branch."""
    assert evaluate_condition("enrich.risk_level == 'high'", outputs={}) is False


def test_missing_key_within_a_present_step_is_false() -> None:
    assert (
        evaluate_condition(
            "enrich.risk_level == 'high'", outputs={"enrich": {"other": 1}}
        )
        is False
    )


def test_a_missing_value_is_false_even_for_a_negated_comparison() -> None:
    """`!=` against absent data must not accidentally read as "true".

    Treating a missing output as `None` would make `s.k != 'x'` true and run a
    branch on data that was never produced.
    """
    assert evaluate_condition("s.k != 'x'", outputs={}) is False


def test_ordering_against_a_non_comparable_value_is_false() -> None:
    """`'high' > 3` is a TypeError in Python; here it is simply a false branch."""
    assert evaluate_condition("s.k > 3", outputs={"s": {"k": "high"}}) is False


# --- everything outside the grammar is rejected -----------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        "__import__('os').system('rm -rf /')",
        "().__class__.__bases__[0].__subclasses__()",
        "open('/etc/passwd').read()",
        "enrich.__class__",
        "1 if exec('x=1') else 0",
        "eval('1+1') == 2",
        "s.k == __import__('sys').version",
        "s.__dict__ == 1",
        "s.__class__ == 1",
        "__dict__.k == 1",
        "_private.k == 1",
        "s._k == 1",
        "s.k.__class__ == 1",
        "getattr(s, 'k') == 1",
        "s.k == 1; import os",
        "s.k == 1 and s.j == 2",
        "s.k == 1 or True",
        "not s.k == 1",
        "lambda: 1",
        "[s.k for s in ()] == []",
        "{'a': 1} == {}",
        "s.k in ('a', 'b')",
        "s.k is None",
        "s.k == 1 if True else 2",
        "(s.k) == 1",
        "s.k + 1 == 2",
        "s['k'] == 1",
        "s.k[0] == 1",
        "print(1) == None",
        "",
        "   ",
        "s.k",
        "== 1",
        "s.k ==",
        "s == 1",
        "s.k.j == 1",
        "s.k === 1",
        "s.k = 1",
        "s.k == 'unterminated",
        "s.k == undefined_name",
        "s.k == True",
        "s.k == None",
    ],
)
def test_rejects_anything_outside_the_grammar(hostile: str) -> None:
    with pytest.raises(ConditionSyntaxError):
        evaluate_condition(hostile, outputs={})


def test_a_string_literal_may_contain_grammar_characters() -> None:
    """Rejecting hostile input must not reject legitimate text."""
    assert (
        evaluate_condition(
            "s.k == 'a == b'", outputs={"s": {"k": "a == b"}}
        )
        is True
    )


def test_a_hostile_string_is_compared_not_interpreted() -> None:
    """The one place attacker-controlled text is allowed: inside a quoted literal.

    Uses double quotes around a payload containing single quotes, since the
    grammar has no escape sequence — a literal cannot contain its own delimiter.
    """
    payload = "__import__('os').system('rm -rf /')"

    assert (
        evaluate_condition(f's.k == "{payload}"', outputs={"s": {"k": payload}}) is True
    )
    assert evaluate_condition(f's.k == "{payload}"', outputs={"s": {"k": "x"}}) is False


def test_the_module_contains_no_dynamic_execution_call() -> None:
    """A source-level guard, because the cost of regressing this is arbitrary RCE.

    A future refactor reaching for `eval` to "simplify" the parser would pass
    every behavioural test above.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "workflow_definitions" / "conditions.py"
    ).read_text(encoding="utf-8")

    # `re.compile` is the parser itself, so bare `compile(` is matched rather
    # than the substring, which would flag it.
    forbidden = ("eval(", "exec(", "__import__", "literal_eval", "__builtins__")
    for token in forbidden:
        assert token not in source, (
            f"conditions.py contains `{token}` — a workflow condition is "
            "user-authored, so any dynamic execution path is remote code execution."
        )
    assert not re.search(r"(?<!re\.)\bcompile\(", source), (
        "conditions.py calls compile() other than re.compile()."
    )


# --- parsing is available separately, for authoring-time validation ---------


def test_parse_condition_accepts_a_valid_condition() -> None:
    parsed = parse_condition("enrich.risk_level == 'high'")

    assert parsed.step_id == "enrich"
    assert parsed.key == "risk_level"
    assert parsed.operator == "=="
    assert parsed.literal == "high"


def test_parse_condition_rejects_a_malformed_condition() -> None:
    with pytest.raises(ConditionSyntaxError):
        parse_condition("enrich.risk_level ~= 'high'")


# --- authoring-time validation ----------------------------------------------


def _definition_with_condition(condition: str | None) -> WorkflowDefinitionCreate:
    return WorkflowDefinitionCreate(
        definition_id="wf-1",
        name="Triage",
        version="v1",
        allowed_capability_refs=["rag.query", "analytics.peer_context"],
        steps=[
            WorkflowStepDefinition(
                step_id="enrich",
                label="Enrich",
                capability_ref="analytics.peer_context",
            ),
            WorkflowStepDefinition(
                step_id="summarise",
                label="Summarise",
                capability_ref="rag.query",
                condition=condition,
            ),
        ],
    )


def test_a_malformed_condition_is_rejected_at_authoring_time() -> None:
    """Rejected on create, not on every run.

    An unparseable condition that only fails at execution breaks the workflow
    long after whoever wrote it has moved on.
    """
    result = validate_workflow_definition_payload(
        _definition_with_condition("enrich.risk_level ~= 'high'")
    )

    assert result.valid is False
    assert any("invalid condition" in error for error in result.errors)


def test_a_hostile_condition_is_rejected_at_authoring_time() -> None:
    result = validate_workflow_definition_payload(
        _definition_with_condition("__import__('os').system('rm -rf /')")
    )

    assert result.valid is False


def test_a_valid_condition_passes_validation() -> None:
    result = validate_workflow_definition_payload(
        _definition_with_condition("enrich.risk_level == 'high'")
    )

    assert result.valid is True, result.errors


def test_a_condition_referencing_an_unknown_step_is_rejected() -> None:
    result = validate_workflow_definition_payload(
        _definition_with_condition("nosuchstep.risk_level == 'high'")
    )

    assert result.valid is False
    assert any("unknown step" in error for error in result.errors)


def test_a_condition_referencing_a_later_step_is_rejected() -> None:
    """A forward reference always evaluates false, so the step never runs.

    Silently never running is the most expensive authoring mistake to
    diagnose — nothing errors, the workflow just quietly does less.
    """
    result = validate_workflow_definition_payload(
        _definition_with_condition("summarise.risk_level == 'high'")
    )

    assert result.valid is False
    assert any("does not run before it" in error for error in result.errors)


def test_no_condition_is_valid() -> None:
    assert validate_workflow_definition_payload(_definition_with_condition(None)).valid
