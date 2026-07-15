"""Tests for config overlay merge semantics (BL-044, config.04)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hypothesis import given
from hypothesis import strategies as st
import pytest
import yaml

from config.overlay import OverlayError, apply_overlays, merge_config_layers
from config.schema import DomainConfig

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
    base = {
        "ui": {
            "default_entity_type": "provider",
            "display_fields": {"claim": {"title": "claim_id"}},
        }
    }
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
    assert merge_config_layers(
        {"llm": {"api_key_env_var": "X"}}, {"llm": {"api_key_env_var": None}}
    ) == {"llm": {"api_key_env_var": None}}


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


@st.composite
def _type_stable_stack(
    draw: st.DrawFn,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Generate (base, A, B) that conform to one shared random shape.

    A "shape" is a skeleton nested dict where every path is fixed, up front,
    as either a mapping node or a leaf (scalar/list) slot. ``base``, ``A``,
    and ``B`` are then sampled independently against that same shape: each
    layer may omit any key, but where a key is present it is always a dict
    at a mapping path and never a dict at a leaf path. This is exactly the
    "no layer changes a key's kind" precondition the amended ADR 0001
    associativity claim requires (see docs/superpowers/specs/
    2026-07-15-bl044-config-overlay-design.md).
    """

    def shape(depth: int) -> Any:
        if depth == 0 or draw(st.booleans()):
            return "leaf"
        return {
            draw(st.text(max_size=4)): shape(depth - 1)
            for _ in range(draw(st.integers(0, 3)))
        }

    skeleton = shape(3)
    if skeleton == "leaf":
        skeleton = {}

    def sample(node: Any) -> Any:
        if node == "leaf":
            return draw(st.one_of(_scalars, st.lists(_scalars, max_size=3)))
        return {
            key: sample(child)
            for key, child in node.items()
            if draw(st.booleans())  # each layer may omit keys
        }

    return sample(skeleton), sample(skeleton), sample(skeleton)


@given(stack=_type_stable_stack())
def test_merge_is_associative_on_type_stable_stacks(
    stack: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    base, a, b = stack
    assert merge_config_layers(merge_config_layers(base, a), b) == merge_config_layers(
        base, merge_config_layers(a, b)
    )


def test_merge_type_flip_is_left_to_right_not_associative() -> None:
    """Type-changing layers are applied left-to-right (ADR 0001 boundary):
    grouping differs when a middle layer collapses a dict — this pins the
    documented application-order semantics."""
    base = {"k": {"z": 1}}
    a = {"k": 5}
    b = {"k": {"w": 2}}
    assert merge_config_layers(merge_config_layers(base, a), b) == {"k": {"w": 2}}
    assert merge_config_layers(base, merge_config_layers(a, b)) == {
        "k": {"z": 1, "w": 2}
    }


@given(base=_configs, overlay=_configs)
def test_overlay_lists_and_scalars_always_win(
    base: dict[str, Any], overlay: dict[str, Any]
) -> None:
    merged = merge_config_layers(base, overlay)
    for key, value in overlay.items():
        if not isinstance(value, dict):
            assert merged[key] == value


def _write_yaml(path: Path, data: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _parse_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


BASE = {"domain": {"name": "medicare_fraud"}, "capabilities": {"peer_stats": True}}


def test_apply_overlays_merges_matching_overlay(tmp_path: Path) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"peer_stats": False}},
    )
    merged = apply_overlays(BASE, [overlay], parse=_parse_yaml)
    assert merged["capabilities"]["peer_stats"] is False
    assert "overlay_for" not in merged  # metadata key stripped before merge


def test_apply_overlays_skips_domain_mismatch_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "af_housing", "capabilities": {"peer_stats": False}},
    )
    with caplog.at_level(logging.WARNING, logger="config.overlay"):
        merged = apply_overlays(BASE, [overlay], parse=_parse_yaml)
    assert merged["capabilities"]["peer_stats"] is True  # untouched
    assert any(
        "af_housing" in record.message and "medicare_fraud" in record.message
        for record in caplog.records
    )


def test_apply_overlays_missing_overlay_for_raises(tmp_path: Path) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml", {"capabilities": {"peer_stats": False}}
    )
    with pytest.raises(OverlayError, match="overlay_for"):
        apply_overlays(BASE, [overlay], parse=_parse_yaml)


def test_apply_overlays_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "medicare_fraud", "embeddngs": {"provider": "local"}},
    )
    with pytest.raises(OverlayError, match="embeddngs"):
        apply_overlays(BASE, [overlay], parse=_parse_yaml)


def test_apply_overlays_stacks_in_declared_order(tmp_path: Path) -> None:
    first = _write_yaml(
        tmp_path / "a.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"gnn": False}},
    )
    second = _write_yaml(
        tmp_path / "b.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"gnn": True}},
    )
    merged = apply_overlays(BASE, [first, second], parse=_parse_yaml)
    assert merged["capabilities"]["gnn"] is True  # last wins


def test_apply_overlays_known_keys_track_domain_config() -> None:
    # Guard: every top-level key DomainConfig defines is accepted in overlays.
    from config.overlay import known_top_level_keys

    assert set(DomainConfig.model_fields) <= known_top_level_keys()
