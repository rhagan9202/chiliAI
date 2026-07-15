# BL-044 Config Base + Overlay Layering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `CHILI_CONFIG_OVERLAY_PATH` layers environment overlays onto a base domain config via deep-merged mappings + wholesale list/scalar replacement, guarded by `overlay_for`, so `medicare_fraud_dev.yaml` shrinks to only its dev-specific overrides — per `docs/superpowers/specs/2026-07-15-bl044-config-overlay-design.md`.

**Architecture:** A pure merge function plus overlay-file validation live in new `backend/config/overlay.py`; `load_config` applies overlays after parsing the base and before `model_validate`, on every load path (explicit/env/pointer). Overlays live in new `backend/config/overlays/` (never listed as packs). The dev YAML is rewritten as an overlay whose merge with the base is proven equivalent to the old full file by a golden test.

**Tech Stack:** Python 3.12, Pydantic v2, PyYAML, hypothesis (new `[dev]` dependency), pytest, pyright --strict.

## Global Constraints

- Merge semantics (spec §1): mappings deep-merge with overlay keys winning recursively; **lists and scalars replace wholesale**; explicit `null` sets the field to `None`; no key-removal semantics.
- `overlay_for: <domain.name>` is REQUIRED in every overlay file; base `domain.name` mismatch ⇒ **skip that overlay with a warning log** (never an error — product-owner ruling); missing `overlay_for` ⇒ `ConfigLoadError`.
- Unknown top-level keys (not in `DomainConfig.model_fields` ∪ `{"overlay_for"}`) ⇒ `ConfigLoadError` naming the key.
- `CHILI_CONFIG_OVERLAY_PATH` is comma-separated; overlays apply in declared order (last wins); empty/unset is a no-op. Field precedence: base ← overlay₁ ← overlay₂. Path-resolution precedence unchanged.
- Overlays live in `backend/config/overlays/` — NOT `config/defaults/` (the pack catalog iterates `defaults/`).
- Run gates from `/home/rdhagan92/chiliAI/backend`: `.venv/bin/pytest tests/config tests/api -q`, `.venv/bin/pyright` (bare — 0 errors), `.venv/bin/ruff check --no-cache .` (clean). Coverage ≥ 85% on `config/`. Full suite runs use `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test` to protect the dev DB.
- Python env is uv-managed: install the new dep with `cd /home/rdhagan92/chiliAI/backend && uv pip install -e ".[dev]"` after editing pyproject.
- All commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Live verification happens in-sprint (Task 5 Step 4 is reserved for the controller/main session — subagents must not run Docker commands).

---

### Task 1: `merge_config_layers` — the pure merge + property tests

**Files:**
- Create: `backend/config/overlay.py`
- Create: `backend/tests/config/test_overlay.py`
- Modify: `backend/pyproject.toml:29-36` (add `hypothesis` to the `dev` extra, alphabetical position after `httpx2>=2.0`)

**Interfaces:**
- Produces: `merge_config_layers(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]` — pure, never mutates inputs. Tasks 2–4 consume it verbatim.

- [ ] **Step 1: Add the dependency.** In `backend/pyproject.toml`, inside `dev = [`, insert `"hypothesis>=6.100",` between `"httpx2>=2.0",` and `"moto[s3]>=5.0",`. Then run:

```bash
cd /home/rdhagan92/chiliAI/backend && uv pip install -e ".[dev]" && .venv/bin/python -c "import hypothesis; print(hypothesis.__version__)"
```

Expected: a version ≥ 6.100 prints.

- [ ] **Step 2: Write the failing tests** — create `backend/tests/config/test_overlay.py`:

```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/config/test_overlay.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'config.overlay'`.

- [ ] **Step 4: Implement** — create `backend/config/overlay.py`:

```python
"""Base + environment overlay layering for domain configuration (config.04).

Merge semantics (ADR 0001): mappings deep-merge with overlay keys winning
recursively; lists and scalars replace wholesale; an explicit ``null`` in an
overlay sets the field to ``None``. There are no key-removal semantics —
absence falls through to the base value or the schema default.
"""

from __future__ import annotations

from typing import Any


def merge_config_layers(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    """Return ``base`` with ``overlay`` layered on top (pure; inputs untouched)."""

    merged: dict[str, Any] = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = merge_config_layers(
                base_value, overlay_value
            )
        else:
            merged[key] = overlay_value
    return merged


__all__ = ["merge_config_layers"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/config/test_overlay.py -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: all tests PASS (hypothesis runs ~100 cases per property), pyright 0 errors, ruff clean.

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/config/overlay.py backend/tests/config/test_overlay.py backend/pyproject.toml
git commit -m "feat(config): pure overlay merge — deep-merge mappings, replace lists/scalars (BL-044)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Overlay-file validation + `apply_overlays`

**Files:**
- Modify: `backend/config/overlay.py`
- Test: `backend/tests/config/test_overlay.py`

**Interfaces:**
- Consumes: Task 1's `merge_config_layers`; the loader's `ConfigLoadError` (`from config.loader import ...` would be circular — so `apply_overlays` raises `config.overlay.OverlayError` and Task 3 wraps it; see Step 3).
- Produces: `apply_overlays(base_data: dict[str, Any], overlay_paths: list[Path], *, parse: Callable[[Path], dict[str, Any]]) -> dict[str, Any]` and `OverlayError(Exception)`. The `parse` callable is injected by the loader (its existing `_read_file`+`_parse_content` composed), keeping overlay.py dependency-light and reusing the loader's YAML/JSON handling without a circular import. `OVERLAY_FOR_KEY = "overlay_for"` module constant.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/config/test_overlay.py` (extend the imports: `import logging`, `from pathlib import Path`, `import pytest`, `import yaml`, and `from config.overlay import OverlayError, apply_overlays`; also `from config.schema import DomainConfig` for the known-keys test):

```python
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
    overlay = _write_yaml(tmp_path / "dev.yaml", {"capabilities": {"peer_stats": False}})
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
        tmp_path / "a.yaml", {"overlay_for": "medicare_fraud", "capabilities": {"gnn": False}}
    )
    second = _write_yaml(
        tmp_path / "b.yaml", {"overlay_for": "medicare_fraud", "capabilities": {"gnn": True}}
    )
    merged = apply_overlays(BASE, [first, second], parse=_parse_yaml)
    assert merged["capabilities"]["gnn"] is True  # last wins


def test_apply_overlays_known_keys_track_domain_config() -> None:
    # Guard: every top-level key DomainConfig defines is accepted in overlays.
    from config.overlay import _known_top_level_keys

    assert set(DomainConfig.model_fields) <= _known_top_level_keys()
```

Note: the last test imports a private helper from the module under test in the SAME package's test dir — check whether `tests/config` is inside pyright's include scope with `reportPrivateUsage`; if pyright flags it, make the helper public (`known_top_level_keys`) instead and update both the test and Step 3's code accordingly (the repo rule is: never suppress; promote to public).

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/config/test_overlay.py -q`
Expected: new tests FAIL with `ImportError` (`OverlayError`, `apply_overlays` undefined); Task 1 tests still pass.

- [ ] **Step 3: Implement** — extend `backend/config/overlay.py` (new imports: `import logging`, `from collections.abc import Callable`, `from pathlib import Path`; module logger `logger = logging.getLogger(__name__)`; extend `__all__` case-sensitively):

```python
OVERLAY_FOR_KEY = "overlay_for"


class OverlayError(Exception):
    """Raised when an overlay file is structurally invalid."""


def _known_top_level_keys() -> set[str]:
    from config.schema import DomainConfig  # local import: avoid import cycles

    return set(DomainConfig.model_fields) | {OVERLAY_FOR_KEY}


def apply_overlays(
    base_data: dict[str, Any],
    overlay_paths: list[Path],
    *,
    parse: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    """Layer each overlay onto ``base_data`` in declared order.

    An overlay whose ``overlay_for`` does not match the base's
    ``domain.name`` is skipped with a warning (hot-swap safety — see ADR
    0001); a missing ``overlay_for`` or an unknown top-level key raises
    ``OverlayError``.
    """

    base_domain = base_data.get("domain", {})
    base_name = base_domain.get("name") if isinstance(base_domain, dict) else None
    merged = base_data
    known_keys = _known_top_level_keys()
    for path in overlay_paths:
        overlay = parse(path)
        if OVERLAY_FOR_KEY not in overlay:
            raise OverlayError(
                f"Overlay {path} is missing the required '{OVERLAY_FOR_KEY}' key."
            )
        unknown = sorted(set(overlay) - known_keys)
        if unknown:
            raise OverlayError(
                f"Overlay {path} contains unknown top-level keys {unknown}. "
                "Valid keys are the DomainConfig sections plus 'overlay_for'."
            )
        target = overlay[OVERLAY_FOR_KEY]
        if target != base_name:
            logger.warning(
                "Skipping overlay %s: overlay_for=%r does not match base "
                "domain.name=%r (hot-swap safety, ADR 0001).",
                path,
                target,
                base_name,
            )
            continue
        payload = {k: v for k, v in overlay.items() if k != OVERLAY_FOR_KEY}
        merged = merge_config_layers(merged, payload)
    return merged
```

- [ ] **Step 4: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/config/test_overlay.py -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: PASS / 0 errors / clean.

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/config/overlay.py backend/tests/config/test_overlay.py
git commit -m "feat(config): apply_overlays — overlay_for guard, unknown-key rejection, ordered stacking (BL-044)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Loader integration — `CHILI_CONFIG_OVERLAY_PATH`

**Files:**
- Modify: `backend/config/loader.py` (`load_config` body ~lines 21-40, TODO at :31)
- Test: `backend/tests/config/test_loader.py`

**Interfaces:**
- Consumes: Task 2's `apply_overlays`/`OverlayError`.
- Produces: `load_config(path=None)` behavior: after `_parse_content`, if `CHILI_CONFIG_OVERLAY_PATH` is set and non-empty, split on commas (strip whitespace, drop empty segments), apply overlays in order, then `_validate`. `OverlayError` is re-raised as `ConfigLoadError`. `load_active_config` inherits this automatically (it delegates).

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/config/test_loader.py` (READ the module first and reuse its existing fixtures for writing temp config files; the assertions below are normative):

```python
def test_load_config_applies_env_overlay(tmp_path, monkeypatch) -> None:
    # Minimal valid base: reuse/adapt this module's existing minimal-config helper
    # if one exists; otherwise copy an existing minimal valid config dict used by
    # other tests in this file.
    base_path = _write_minimal_config(tmp_path / "base.yaml")  # existing-style helper
    base_domain_name = _load_yaml(base_path)["domain"]["name"]
    overlay_path = tmp_path / "dev-overlay.yaml"
    overlay_path.write_text(
        yaml.safe_dump(
            {"overlay_for": base_domain_name, "capabilities": {"rag_chat": False}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(overlay_path))
    config = load_config(base_path)
    assert config.capabilities.rag_chat is False


def test_load_config_overlay_env_unset_is_noop(tmp_path, monkeypatch) -> None:
    base_path = _write_minimal_config(tmp_path / "base.yaml")
    monkeypatch.delenv("CHILI_CONFIG_OVERLAY_PATH", raising=False)
    config = load_config(base_path)  # must not raise
    assert config.domain.name


def test_load_config_overlay_error_becomes_config_load_error(tmp_path, monkeypatch) -> None:
    base_path = _write_minimal_config(tmp_path / "base.yaml")
    bad_overlay = tmp_path / "bad.yaml"
    bad_overlay.write_text(yaml.safe_dump({"capabilities": {}}), encoding="utf-8")  # no overlay_for
    monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(bad_overlay))
    with pytest.raises(ConfigLoadError, match="overlay_for"):
        load_config(base_path)


def test_load_config_overlay_paths_comma_separated(tmp_path, monkeypatch) -> None:
    base_path = _write_minimal_config(tmp_path / "base.yaml")
    name = _load_yaml(base_path)["domain"]["name"]
    a = tmp_path / "a.yaml"
    a.write_text(yaml.safe_dump({"overlay_for": name, "capabilities": {"gnn": False}}), encoding="utf-8")
    b = tmp_path / "b.yaml"
    b.write_text(yaml.safe_dump({"overlay_for": name, "capabilities": {"gnn": True}}), encoding="utf-8")
    monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", f" {a} , {b} ")
    config = load_config(base_path)
    assert config.capabilities.gnn is True
```

(`_write_minimal_config` / `_load_yaml` stand for the module's actual helpers — adapt names after reading the file; if no minimal-config helper exists, add one private to the test module using the smallest dict that validates.)

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/config/test_loader.py -q -k overlay`
Expected: FAIL (overlay env var ignored / names undefined).

- [ ] **Step 3: Implement.** In `backend/config/loader.py`: add `from config.overlay import OverlayError, apply_overlays` to the imports; replace the TODO comment's first line (keep the secrets/hot-reload clauses of the TODO) and extend `load_config`:

```python
    # TODO(production): Add secrets resolution for ${ENV_VAR} placeholders in
    # config values. Cache the loaded DomainConfig and support hot-reload via
    # file watcher or API endpoint. See docs/archive/config_engine_plan.md for
    # the historical config engine plan.
    resolved = _resolve_path(path)

    raw = _read_file(resolved)
    data = _parse_content(raw, resolved)
    overlay_paths = _overlay_paths_from_env()
    if overlay_paths:
        try:
            data = apply_overlays(data, overlay_paths, parse=_parse_config_file)
        except OverlayError as exc:
            raise ConfigLoadError(str(exc)) from exc
    return _validate(data)
```

and add the two helpers near the other private helpers:

```python
def _overlay_paths_from_env() -> list[Path]:
    raw = os.environ.get("CHILI_CONFIG_OVERLAY_PATH", "")
    return [Path(part.strip()) for part in raw.split(",") if part.strip()]


def _parse_config_file(path: Path) -> dict[str, Any]:
    return _parse_content(_read_file(path), path)
```

- [ ] **Step 4: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/config -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: PASS / 0 errors / clean. Watch for pre-existing loader tests that run with `CHILI_CONFIG_OVERLAY_PATH` leaking from the environment — none should exist, but if any test breaks, isolate env with `monkeypatch.delenv`.

- [ ] **Step 5: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/config/loader.py backend/tests/config/test_loader.py
git commit -m "feat(config): CHILI_CONFIG_OVERLAY_PATH — ordered env overlays in load_config (BL-044)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Rewrite `medicare_fraud_dev.yaml` as an overlay + golden equivalence test

**Files:**
- Create: `backend/config/overlays/medicare_fraud_dev.yaml`
- Delete: `backend/config/defaults/medicare_fraud_dev.yaml`
- Test: `backend/tests/config/test_overlay.py` (golden test), `backend/tests/api/test_config_router.py:19,88-98` (fixture update)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: the overlay file every doc/example references; the measured line-reduction number for the story annotation.

- [ ] **Step 1: Capture the golden baseline BEFORE rewriting.** The equivalence test compares `base ⊕ overlay` against the OLD full dev config. Preserve the old file's parsed content as the test's expectation via git:

```bash
cd /home/rdhagan92/chiliAI
git show HEAD:backend/config/defaults/medicare_fraud_dev.yaml > /tmp/old_medicare_fraud_dev.yaml
```

- [ ] **Step 2: Write the overlay.** Create `backend/config/overlays/medicare_fraud_dev.yaml` with EXACTLY this structure — section content copied VERBATIM from the old `backend/config/defaults/medicare_fraud_dev.yaml` (use `git show HEAD:...` as the source):

```yaml
# Dev-environment overlay for the medicare_fraud base pack (ADR 0001).
# Layers onto config/defaults/medicare_fraud.yaml via CHILI_CONFIG_OVERLAY_PATH.
overlay_for: medicare_fraud

# --- dev infra sections (copied verbatim from the old full dev file) ---
analytics: <verbatim from old file>
database: <verbatim>
embeddings: <verbatim>
events: <verbatim>
graph: <verbatim>
llm: <verbatim>
monitoring: <verbatim>
storage: <verbatim>
vectorstore: <verbatim>

# --- dev knob flips ---
capabilities:
  peer_stats: false   # base sets true; dev runs without the peerstats stage

# list-replace semantics (ADR 0001): the whole policy_rules list is restated
# because dev changes one threshold inside it.
policy_rules: <verbatim from old file>

# deep-merge addition: facility card in the workbench; the rest of ui comes
# from the base.
ui:
  display_fields:
    facility: <verbatim facility block from old file>
```

The `<verbatim ...>` markers are instructions to you, not literal content — replace each with the exact YAML from the old file. Do NOT include `domain`, `entities`, `relationships`, `records`, `ingestion`, `rag`, `alerts`, or the rest of `ui`/`capabilities` — those are identical to base or covered by deep-merge. Then delete `backend/config/defaults/medicare_fraud_dev.yaml` (`git rm`).

- [ ] **Step 3: Write the golden equivalence test** — append to `backend/tests/config/test_overlay.py`:

```python
REPO_CONFIG = Path(__file__).resolve().parent.parent.parent / "config"


def test_medicare_dev_overlay_reproduces_old_full_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """base ⊕ dev-overlay must equal the retired full dev file, except:
    - merged config KEEPS base's `peer_stats` section (old dev file omitted
      it; the capability flag `capabilities.peer_stats: false` gates it off);
    - merged `capabilities.peer_stats` is False (old file expressed this by
      omission; schema default is False, so validated output is identical).
    """
    import subprocess

    from config.loader import load_config

    old_raw = subprocess.run(
        ["git", "show", "HEAD~1:backend/config/defaults/medicare_fraud_dev.yaml"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_CONFIG,
    ).stdout
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
```

NOTE the `HEAD~1` reference assumes this test lands in the SAME commit that deletes the old file (so at test-run time the old file is one commit back). If the git-history dependency proves brittle under CI's checkout depth, replace the `git show` with a checked-in snapshot: copy the old file to `backend/tests/config/fixtures/medicare_fraud_dev_full_snapshot.yaml` in this same commit and load it directly — prefer this fixture approach if CI uses a shallow clone (check `.github/workflows/ci.yml` checkout settings; `fetch-depth` unset means depth 1 ⇒ USE THE FIXTURE APPROACH).

- [ ] **Step 4: Update `backend/tests/api/test_config_router.py`.** Line 19's `MEDICARE_DEV_YAML = DEFAULTS_DIR / "medicare_fraud_dev.yaml"` now points at a deleted file, and `test_dev_config_returns_ui_features` (line ~88) loads it as a full config. Preserve the test's subject (dev config serves UI features) by loading base + overlay:

```python
OVERLAYS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "overlays"
MEDICARE_DEV_OVERLAY = OVERLAYS_DIR / "medicare_fraud_dev.yaml"
```

and in the test:

```python
    def test_dev_config_returns_ui_features(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CHILI_CONFIG_OVERLAY_PATH", str(MEDICARE_DEV_OVERLAY))
        app = create_app()
        config = load_config(MEDICARE_YAML)
        ...  # rest unchanged
```

(Adapt to the class/fixture style actually present; keep every existing assertion.)

- [ ] **Step 5: Run the affected suites + measure the reduction**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/config tests/api -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: PASS / 0 / clean.

```bash
OLD=$(git show HEAD:backend/config/defaults/medicare_fraud_dev.yaml | wc -l)
NEW=$(wc -l < backend/config/overlays/medicare_fraud_dev.yaml)
echo "old=$OLD new=$NEW reduction=$(( (OLD-NEW)*100/OLD ))%"
```

Record the printed percentage — it goes in the commit message and story annotation (expected 60–70%; the ADR documents why not 80%).

- [ ] **Step 6: Commit** (single commit so the golden test's `HEAD~1`/fixture story holds)

```bash
cd /home/rdhagan92/chiliAI
git add -A backend/config backend/tests
git commit -m "refactor(config): medicare_fraud_dev.yaml becomes a minimal overlay (<measured>% smaller) (BL-044)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: ADR + docs + story closeout (+ controller-run live verification)

**Files:**
- Create: `docs/architecture/decisions/0001-config-overlay-merge-semantics.md`
- Modify: `backend/README.md`, `backend/config/README.md`, `docs/architecture.md` (domain-config model section), `docs/backlog/config.md` (config.04 → done), `docs/project/planning/backlog.md` (BL-044 status), `docs/project/planning/sprints/2026-27.md` (progress entry)

**Interfaces:**
- Consumes: everything shipped in Tasks 1–4 plus the measured reduction percentage.

- [ ] **Step 1: Write the ADR** — `docs/architecture/decisions/0001-config-overlay-merge-semantics.md` (new directory; this is the repo's first ADR):

```markdown
# ADR 0001 — Config overlay merge semantics

Date: 2026-07-15 · Status: accepted · Story: BL-044 / config.04

## Context
Environment configs duplicated the whole domain surface to flip a handful of
knobs (medicare_fraud.yaml vs medicare_fraud_dev.yaml). We need overlay
layering with unambiguous, testable merge semantics, safe under runtime
domain-pack hot-swap (the overlay env var survives a swap).

## Decision
1. Mappings deep-merge; overlay keys win recursively.
2. **Lists and scalars replace wholesale** (no list-merge-by-key). Measured
   against the real base→dev diff, the only list-level change was one scalar
   inside `policy_rules` — restating that block is cheaper than the
   complexity and murkier algebra of keyed list merging.
3. Explicit `null` sets a field to `None`; absence falls through to
   base/schema defaults; there are no key-removal semantics.
4. Every overlay declares `overlay_for: <domain.name>`. A base-domain
   mismatch skips the overlay with a warning (product-owner ruling
   2026-07-15) so hot-swapping packs never applies a foreign overlay and
   never fails the swap. Missing `overlay_for` or unknown top-level keys are
   hard errors.
5. Overlays live in `backend/config/overlays/`, outside the pack catalog.
6. `CHILI_CONFIG_OVERLAY_PATH` is comma-separated; declared order, last wins.

## Consequences
- The merge is associative with the empty overlay as identity
  (property-tested via hypothesis in `tests/config/test_overlay.py`).
- An overlay touching one element of a list must restate the whole list —
  this held the dev-file reduction to <measured>% rather than ~80%.
- Overlays cannot delete keys; "off" states must be expressible as explicit
  values (e.g. `capabilities.peer_stats: false`).
```

Replace `<measured>` with Task 4's number.

- [ ] **Step 2: Update the docs.** `backend/README.md`: add an "Config overlays" subsection with the worked example (`CHILI_CONFIG_PATH=config/defaults/medicare_fraud.yaml CHILI_CONFIG_OVERLAY_PATH=config/overlays/medicare_fraud_dev.yaml uvicorn ...`) and a pointer to ADR 0001. `backend/config/README.md`: document `overlay.py`, the `overlays/` directory, the guard, and the env var. `docs/architecture.md`: extend the domain-config model section with the overlay layer + precedence line (base ← overlays; path resolution: explicit > pointer > env). Retire any statement that says overlay layering is unimplemented (search: `grep -rn "overlay" docs/architecture.md backend/README.md backend/config/README.md CLAUDE.md .github/`).

- [ ] **Step 3: Story + backlog closeout.** `docs/backlog/config.md`: config.04 → `done`, Done line `**Done:** 2026-07-15 · BL-044 (Sprint 2026-27) · feat/sprint-2026-27-config-overlay`, all AC boxes checked, with two annotations: (1) measured reduction <measured>% vs the AC's "~80%" (list-replace trade-off, ADR 0001), (2) overlay lives in `config/overlays/` not `defaults/` (pack-catalog separation). `docs/project/planning/backlog.md`: BL-044 → done (live-verification wording per what has actually run). `docs/project/planning/sprints/2026-27.md`: append a BL-044 progress entry. Run `backend/.venv/bin/python scripts/backlog_consistency.py` (include any rollup rewrites) then `--check` (exit 0).

- [ ] **Step 4: Live verification — RESERVED FOR THE CONTROLLER (main session).** Not a subagent step. Against `make dev`: (1) restart the API with `CHILI_CONFIG_PATH=/app/config/defaults/medicare_fraud.yaml` + `CHILI_CONFIG_OVERLAY_PATH=/app/config/overlays/medicare_fraud_dev.yaml` and confirm via `GET /config/domain` that a dev knob (e.g. `monitoring.evaluation_interval_seconds`) reflects the overlay; (2) hot-swap to the housing pack with the overlay env still set and confirm the structured skip warning appears in the API log and the served config is clean housing base.

- [ ] **Step 5: Full-suite gates**

Run: `cd /home/rdhagan92/chiliAI/backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: full pass, `config` package ≥ 85%, 0 errors, clean.

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add docs/ backend/README.md backend/config/README.md
git commit -m "docs(config): ADR 0001 overlay semantics; overlay model documented; config.04 closeout (BL-044)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes (already applied)

- Spec coverage: §1→Task 1 (+ADR in Task 5), §2→Tasks 2/4, §3→Task 3, §4→Task 4, §5→Task 5, §6→Tasks 1-4 tests + Task 5 Step 4 live verification. The spec's `test_config_router` fixture decision is resolved in Task 4 Step 4 (base + env overlay, subject preserved).
- Golden-test git-history dependency: mitigated with an explicit fixture-file fallback keyed to CI checkout depth (Task 4 Step 3 note).
- Type consistency: `merge_config_layers` / `apply_overlays(parse=...)` / `OverlayError` names match across Tasks 1-3; loader helpers `_overlay_paths_from_env` / `_parse_config_file` used only within Task 3.
- Helper names in test code marked as stand-ins (`_write_minimal_config`, `_load_yaml`) follow the established convention: assertions normative, names adapted to the module.
