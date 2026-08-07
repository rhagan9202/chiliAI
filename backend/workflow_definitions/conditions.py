"""Restricted grammar for workflow step conditions.

A ``condition`` is authored by a user and stored in a multi-tenant system, so
evaluating it with ``eval`` would be remote code execution. The grammar here is
deliberately tiny — one comparison, no operators, no calls, no attribute
traversal — and anything outside it is a syntax error rather than a
best-effort parse:

    <step_id>.<key> <op> <literal>

``op`` is one of ``== != > >= < <=``. ``literal`` is a quoted string, a number,
``true``, ``false`` or ``null``. That is the whole language. It is smaller than
most authors will eventually want, and widening it later is a deliberate
decision with its own tests; guessing at intent inside an evaluator is how
these grammars grow an expression parser and then an interpreter.

There is no dynamic execution path anywhere in this module, and a test asserts
that at the source level — a refactor reaching for ``eval`` to "simplify" the
parser would otherwise pass every behavioural test.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

__all__ = [
    "ConditionSyntaxError",
    "ParsedCondition",
    "evaluate_condition",
    "parse_condition",
]

ConditionOperator: TypeAlias = Literal["==", "!=", ">", ">=", "<", "<="]

# Longest-first, so `>=` is not mis-read as `>` followed by a stray `=`.
_OPERATORS: Final[tuple[str, ...]] = ("==", "!=", ">=", "<=", ">", "<")

# Must start with a letter, and `__` is rejected anywhere. Lookups are plain
# dict access, so `s.__dict__` would already just miss and evaluate False —
# but a grammar that *admits* dunder names invites a future refactor to
# attribute-based lookup, and that refactor would be instantly exploitable.
_IDENTIFIER = r"[A-Za-z](?:[A-Za-z0-9_-]*[A-Za-z0-9])?"

_CONDITION_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"""
    \A\s*
    (?P<step_id>{_IDENTIFIER})
    \.
    (?P<key>{_IDENTIFIER})
    \s*
    (?P<operator>==|!=|>=|<=|>|<)
    \s*
    (?P<literal>
        '[^']*'          # single-quoted string
      | "[^"]*"          # double-quoted string
      | -?\d+\.\d+       # float
      | -?\d+            # integer
      | true | false | null
    )
    \s*\Z
    """,
    re.VERBOSE,
)


class ConditionSyntaxError(ValueError):
    """A condition string is not expressible in the restricted grammar.

    Deliberately raised rather than evaluated as ``False``: a condition that
    cannot be parsed is an authoring mistake, and silently treating it as a
    false branch would skip a step forever without telling anyone.
    """


@dataclass(frozen=True)
class ParsedCondition:
    """A single parsed comparison."""

    step_id: str
    key: str
    operator: ConditionOperator
    literal: str | float | int | bool | None


def parse_condition(condition: str) -> ParsedCondition:
    """Parse a condition, raising ``ConditionSyntaxError`` if it is not valid.

    Exposed separately from evaluation so a definition can be rejected at
    authoring time (HTTP 422) rather than failing every run.
    """

    match = _CONDITION_PATTERN.match(condition)
    if match is None:
        raise ConditionSyntaxError(
            f"Condition {condition!r} is not of the form "
            "`<step_id>.<key> <op> <literal>` with op in "
            f"{', '.join(_OPERATORS)}."
        )
    operator = match.group("operator")
    return ParsedCondition(
        step_id=match.group("step_id"),
        key=match.group("key"),
        # The pattern only admits the six operators, so this is exact.
        operator=_as_operator(operator),
        literal=_parse_literal(match.group("literal")),
    )


def evaluate_condition(
    condition: str,
    *,
    outputs: Mapping[str, Mapping[str, object]],
) -> bool:
    """Evaluate a condition against the outputs of completed steps.

    A reference to a step that has not run, or to a key it did not produce,
    evaluates ``False`` for every operator — including ``!=``. Treating a
    missing value as ``None`` would make ``s.k != 'x'`` true and run a branch
    on data that was never produced.
    """

    parsed = parse_condition(condition)
    step_output = outputs.get(parsed.step_id)
    if step_output is None or parsed.key not in step_output:
        return False
    return _compare(step_output[parsed.key], parsed.operator, parsed.literal)


def _as_operator(raw: str) -> ConditionOperator:
    if raw == "==":
        return "=="
    if raw == "!=":
        return "!="
    if raw == ">=":
        return ">="
    if raw == "<=":
        return "<="
    if raw == ">":
        return ">"
    return "<"


def _parse_literal(raw: str) -> str | float | int | bool | None:
    if raw.startswith("'") or raw.startswith('"'):
        return raw[1:-1]
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw == "null":
        return None
    if "." in raw:
        return float(raw)
    return int(raw)


def _compare(
    value: object,
    operator: ConditionOperator,
    literal: str | float | int | bool | None,
) -> bool:
    if operator == "==":
        return bool(value == literal)
    if operator == "!=":
        return bool(value != literal)
    # Ordering comparisons are only meaningful between compatible types.
    # `'high' > 3` raises TypeError in Python; here an author has written a
    # comparison that cannot hold, which is a false branch rather than a
    # crashed workflow.
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    if not isinstance(literal, (int, float)) or isinstance(literal, bool):
        return False
    if operator == ">":
        return value > literal
    if operator == ">=":
        return value >= literal
    if operator == "<":
        return value < literal
    return value <= literal
