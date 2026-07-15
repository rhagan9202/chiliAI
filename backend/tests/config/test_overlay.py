"""Tests for config overlay merge semantics (BL-044, config.04)."""

from __future__ import annotations

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from config.overlay import merge_config_layers

# Nested config-shaped dicts: string keys; scalar / list / nested-dict values.
_scalars = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=8))
_values = st.recursive(
    st.one_of(_scalars, st.lists(_scalars, max_size=3)),
    lambda children: st.dictionaries(st.text(max_size=6), children, max_size=3),
    max_leaves=12,
)
_configs = st.dictionaries(st.text(max_size=6), _values, max_size=4)


def test_merge_overlay_scalar_wins() -> None:
    assert merge_config_layers({"a": 1, "b": 2}, {"b": 9}) == {"a": 1, "b": 9}


def test_merge_recurses_into_nested_mappings() -> None:
    base = {"ui": {"default_entity_type": "provider", "display_fields": {"claim": {"title": "claim_id"}}}}
    overlay = {"ui": {"display_fields": {"facility": {"title": "name"}}}}
    merged = merge_config_layers(base, overlay)
    assert merged["ui"]["default_entity_type"] == "provider"
    assert merged["ui"]["display_fields"] == {
        "claim": {"title": "claim_id"},
        "facility": {"title": "name"},
    }


def test_merge_replaces_lists_wholesale() -> None:
    base = {"policy_rules": [{"id": "a"}, {"id": "b"}]}
    overlay = {"policy_rules": [{"id": "c"}]}
    assert merge_config_layers(base, overlay)["policy_rules"] == [{"id": "c"}]


def test_merge_explicit_none_overrides() -> None:
    assert merge_config_layers({"llm": {"api_key_env_var": "X"}}, {"llm": {"api_key_env_var": None}}) == {
        "llm": {"api_key_env_var": None}
    }


def test_merge_type_change_replaces_wholesale() -> None:
    # A mapping in base replaced by a scalar in overlay (and vice versa) replaces.
    assert merge_config_layers({"a": {"x": 1}}, {"a": 5}) == {"a": 5}
    assert merge_config_layers({"a": 5}, {"a": {"x": 1}}) == {"a": {"x": 1}}


def test_merge_does_not_mutate_inputs() -> None:
    base = {"a": {"x": 1}}
    overlay = {"a": {"y": 2}}
    merge_config_layers(base, overlay)
    assert base == {"a": {"x": 1}}
    assert overlay == {"a": {"y": 2}}


@given(base=_configs)
def test_empty_overlay_is_identity(base: dict[str, Any]) -> None:
    assert merge_config_layers(base, {}) == base


@given(base=_configs, a=_configs, b=_configs)
def test_merge_is_associative(base: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> None:
    assert merge_config_layers(merge_config_layers(base, a), b) == merge_config_layers(
        base, merge_config_layers(a, b)
    )


@given(base=_configs, overlay=_configs)
def test_overlay_lists_and_scalars_always_win(base: dict[str, Any], overlay: dict[str, Any]) -> None:
    merged = merge_config_layers(base, overlay)
    for key, value in overlay.items():
        if not isinstance(value, dict):
            assert merged[key] == value
