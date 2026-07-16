"""Tests for config overlay merge semantics (BL-044, config.04)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, cast

from hypothesis import given
from hypothesis import strategies as st
from pydantic import JsonValue
import pytest
import yaml

from config.overlay import OverlayError, apply_overlays, merge_config_layers
from config.schema import DomainConfig


def _nested(value: JsonValue, key: str) -> JsonValue:
    """Index one level into a ``JsonValue`` known (by test setup) to be a mapping."""
    assert isinstance(value, dict)
    return value[key]


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
    base: dict[str, JsonValue] = {
        "ui": {
            "default_entity_type": "provider",
            "display_fields": {"claim": {"title": "claim_id"}},
        }
    }
    overlay: dict[str, JsonValue] = {
        "ui": {"display_fields": {"facility": {"title": "name"}}}
    }
    merged = merge_config_layers(base, overlay)
    assert _nested(merged["ui"], "default_entity_type") == "provider"
    assert _nested(merged["ui"], "display_fields") == {
        "claim": {"title": "claim_id"},
        "facility": {"title": "name"},
    }


def test_merge_replaces_lists_wholesale() -> None:
    base: dict[str, JsonValue] = {"policy_rules": [{"id": "a"}, {"id": "b"}]}
    overlay: dict[str, JsonValue] = {"policy_rules": [{"id": "c"}]}
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
    base: dict[str, JsonValue] = {"a": {"x": 1}}
    overlay: dict[str, JsonValue] = {"a": {"y": 2}}
    merge_config_layers(base, overlay)
    assert base == {"a": {"x": 1}}
    assert overlay == {"a": {"y": 2}}


@given(base=_configs)
def test_empty_overlay_is_identity(base: dict[str, JsonValue]) -> None:
    assert merge_config_layers(base, {}) == base


type _Skeleton = Literal["leaf"] | dict[str, _Skeleton]


@st.composite
def _type_stable_stack(
    draw: st.DrawFn,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue]]:
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

    def shape(depth: int) -> _Skeleton:
        if depth == 0 or draw(st.booleans()):
            return "leaf"
        return cast(
            dict[str, _Skeleton],
            {
                draw(st.text(max_size=4)): shape(depth - 1)
                for _ in range(draw(st.integers(0, 3)))
            },
        )

    skeleton = shape(3)
    if skeleton == "leaf":
        skeleton = {}

    def sample(node: _Skeleton) -> JsonValue:
        if node == "leaf":
            return cast(
                JsonValue, draw(st.one_of(_scalars, st.lists(_scalars, max_size=3)))
            )
        return {
            key: sample(child)
            for key, child in node.items()
            if draw(st.booleans())  # each layer may omit keys
        }

    return (
        cast(dict[str, JsonValue], sample(skeleton)),
        cast(dict[str, JsonValue], sample(skeleton)),
        cast(dict[str, JsonValue], sample(skeleton)),
    )


@given(stack=_type_stable_stack())
def test_merge_is_associative_on_type_stable_stacks(
    stack: tuple[dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue]],
) -> None:
    base, a, b = stack
    assert merge_config_layers(merge_config_layers(base, a), b) == merge_config_layers(
        base, merge_config_layers(a, b)
    )


def test_merge_type_flip_is_left_to_right_not_associative() -> None:
    """Type-changing layers are applied left-to-right (ADR 0001 boundary):
    grouping differs when a middle layer collapses a dict — this pins the
    documented application-order semantics."""
    base: dict[str, JsonValue] = {"k": {"z": 1}}
    a: dict[str, JsonValue] = {"k": 5}
    b: dict[str, JsonValue] = {"k": {"w": 2}}
    assert merge_config_layers(merge_config_layers(base, a), b) == {"k": {"w": 2}}
    assert merge_config_layers(base, merge_config_layers(a, b)) == {
        "k": {"z": 1, "w": 2}
    }


@given(base=_configs, overlay=_configs)
def test_overlay_lists_and_scalars_always_win(
    base: dict[str, JsonValue], overlay: dict[str, JsonValue]
) -> None:
    merged = merge_config_layers(base, overlay)
    for key, value in overlay.items():
        if not isinstance(value, dict):
            assert merged[key] == value


def _write_yaml(path: Path, data: dict[str, JsonValue]) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _parse_yaml(path: Path) -> dict[str, JsonValue]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return cast(dict[str, JsonValue], loaded)


BASE: dict[str, JsonValue] = {
    "domain": {"name": "medicare_fraud"},
    "capabilities": {"peer_stats": True},
}


BASE_PATH = Path("medicare_fraud.yaml")


def test_apply_overlays_merges_matching_overlay(tmp_path: Path) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"peer_stats": False}},
    )
    merged = apply_overlays(BASE, [overlay], base_path=BASE_PATH, parse=_parse_yaml)
    assert _nested(merged["capabilities"], "peer_stats") is False
    assert "overlay_for" not in merged  # metadata key stripped before merge


def test_apply_overlays_skips_pack_mismatch_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "af_housing", "capabilities": {"peer_stats": False}},
    )
    with caplog.at_level(logging.WARNING, logger="config.overlay"):
        merged = apply_overlays(BASE, [overlay], base_path=BASE_PATH, parse=_parse_yaml)
    assert _nested(merged["capabilities"], "peer_stats") is True  # untouched
    assert any(
        "af_housing" in record.message and "medicare_fraud" in record.message
        for record in caplog.records
    )


def test_apply_overlays_missing_overlay_for_raises(tmp_path: Path) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml", {"capabilities": {"peer_stats": False}}
    )
    with pytest.raises(OverlayError, match="overlay_for"):
        apply_overlays(BASE, [overlay], base_path=BASE_PATH, parse=_parse_yaml)


def test_apply_overlays_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "medicare_fraud", "embeddngs": {"provider": "local"}},
    )
    with pytest.raises(OverlayError, match="embeddngs"):
        apply_overlays(BASE, [overlay], base_path=BASE_PATH, parse=_parse_yaml)


def test_apply_overlays_stacks_in_declared_order(tmp_path: Path) -> None:
    first = _write_yaml(
        tmp_path / "a.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"gnn": False}},
    )
    second = _write_yaml(
        tmp_path / "b.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"gnn": True}},
    )
    merged = apply_overlays(BASE, [first, second], base_path=BASE_PATH, parse=_parse_yaml)
    assert _nested(merged["capabilities"], "gnn") is True  # last wins


def test_apply_overlays_base_without_domain_key_matches_by_pack_stem(
    tmp_path: Path,
) -> None:
    # The guard is pack-scoped (base_path.stem), so a base dict with no
    # "domain" key at all still matches correctly — domain.name is never read.
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"gnn": False}},
    )
    merged = apply_overlays(
        {"capabilities": {"gnn": True}},
        [overlay],
        base_path=BASE_PATH,
        parse=_parse_yaml,
    )
    assert _nested(merged["capabilities"], "gnn") is False  # applied: stem matched


def test_overlay_skips_same_domain_different_pack(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """DE-SynPUF regression: two packs sharing domain.name must NOT share
    an overlay — the guard must key off the base pack's filename stem, not
    domain.name, or a dev overlay for medicare_fraud.yaml silently applies to
    medicare_fraud_cms_desynpuf.yaml too."""
    overlay = _write_yaml(
        tmp_path / "dev.yaml",
        {"overlay_for": "medicare_fraud", "capabilities": {"peer_stats": False}},
    )
    with caplog.at_level(logging.WARNING, logger="config.overlay"):
        merged = apply_overlays(
            BASE,  # domain.name == "medicare_fraud"
            [overlay],
            base_path=Path("/some/dir/medicare_fraud_cms_desynpuf.yaml"),
            parse=_parse_yaml,
        )
    assert _nested(merged["capabilities"], "peer_stats") is True  # untouched: skipped
    assert any(
        "medicare_fraud_cms_desynpuf" in record.message
        and "medicare_fraud" in record.message
        for record in caplog.records
    )


def test_shipped_dev_overlay_passes_unknown_key_guard_and_canary_fails(
    tmp_path: Path,
) -> None:
    """The unknown-key guard fires on realistic content: the SHIPPED dev overlay
    passes, and the same overlay plus one canary typo key is rejected naming it."""
    overlays_dir = Path(__file__).resolve().parent.parent.parent / "config" / "overlays"
    shipped = yaml.safe_load((overlays_dir / "medicare_fraud_dev.yaml").read_text())
    base: dict[str, JsonValue] = {"domain": {"name": "medicare_fraud"}}
    good = _write_yaml(tmp_path / "medicare_fraud_dev.yaml", shipped)
    apply_overlays(base, [good], base_path=Path("medicare_fraud.yaml"), parse=_parse_yaml)  # no raise
    shipped_bad = dict(shipped)
    shipped_bad["embeddngs"] = {"provider": "local"}
    bad = _write_yaml(tmp_path / "bad.yaml", shipped_bad)
    with pytest.raises(OverlayError, match="embeddngs"):
        apply_overlays(base, [bad], base_path=Path("medicare_fraud.yaml"), parse=_parse_yaml)


REPO_CONFIG = Path(__file__).resolve().parent.parent.parent / "config"
DEV_SNAPSHOT = (
    Path(__file__).resolve().parent / "fixtures" / "medicare_fraud_dev_full_snapshot.yaml"
)


def test_medicare_dev_overlay_reproduces_old_full_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """base ⊕ dev-overlay must equal the retired full dev file, except:
    - merged config KEEPS base's `peer_stats` section (old dev file omitted
      it; the capability flag `capabilities.peer_stats: false` gates it off);
    - merged `capabilities.peer_stats` is False (old file expressed this by
      omission; schema default is False, so validated output is identical).

    The retired file (formerly `config/defaults/medicare_fraud_dev.yaml`) is
    preserved verbatim as a checked-in snapshot fixture rather than fetched
    via `git show HEAD~1:...`: CI's checkout is shallow (fetch-depth unset ==
    depth 1 on `actions/checkout@v4`), so history-dependent lookups are not
    available at test-run time.

    The snapshot is FROZEN HISTORY pinning the BL-044 refactor equivalence.
    A deliberate future edit to `defaults/medicare_fraud.yaml` or
    `overlays/medicare_fraud_dev.yaml` is SUPPOSED to break this test: apply
    the same semantic change to the snapshot fixture (keeping the diff
    reviewable) — or, once base/overlay have legitimately diverged far from
    the 2026-07 refactor, retire the test and fixture together.
    """
    from config.loader import load_config

    old_raw = DEV_SNAPSHOT.read_text(encoding="utf-8")
    old_config = DomainConfig.model_validate(yaml.safe_load(old_raw))

    monkeypatch.setenv(
        "CHILI_CONFIG_OVERLAY_PATH", str(REPO_CONFIG / "overlays" / "medicare_fraud_dev.yaml")
    )
    merged = load_config(REPO_CONFIG / "defaults" / "medicare_fraud.yaml")

    old_dump = old_config.model_dump()
    merged_dump = merged.model_dump()
    # Documented exception: base's peer_stats section survives (gated off).
    merged_dump.pop("peer_stats", None)
    old_dump.pop("peer_stats", None)
    assert merged_dump == old_dump
