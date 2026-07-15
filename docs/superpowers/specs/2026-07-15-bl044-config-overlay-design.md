# BL-044 — Config base + environment overlay layering (design)

> Status: approved by product owner 2026-07-15 (one scope ruling recorded below).
> Sprint: 2026-27. Module story: `config.04` — `docs/backlog/config.md`. Requirement: REQ-CONFIG-001.

## Problem

`backend/config/loader.py:31` carries the standing `TODO(production)` for base + env-specific layering. `medicare_fraud.yaml` (228 lines) and `medicare_fraud_dev.yaml` (244 lines) duplicate the entire entity/relationship/records surface to flip a handful of knobs, so environment drift is neither localized nor reviewable. No `CHILI_CONFIG_OVERLAY_PATH`, no documented precedence, no merge tests. config.04 is the ingestion roadmap's named next lever (unblocks ingestion.08/09/13/15, agent.05/10, config.08).

## Product-owner ruling (2026-07-15)

**Cross-domain guard = `overlay_for` skip-with-warning.** Every overlay file declares `overlay_for: <domain.name>`; the loader applies the overlay only when the base config's `domain.name` matches and otherwise skips it with a structured warning log. A runtime hot-swap to another pack therefore runs clean base config (the overlay env var survives the swap harmlessly). Mismatch is not a boot error — a hard error would break hot-swap whenever an overlay is set, since a swap cannot change env vars.

## Empirical basis (base → dev diff, measured 2026-07-15)

- `entities`, `relationships`, `records`, `ingestion`, `rag`, `alerts`, `domain` — byte-identical (the duplication this story deletes).
- Dev-only whole sections: `analytics`, `database`, `embeddings`, `events`, `graph`, `llm`, `monitoring`, `storage`, `vectorstore`.
- `capabilities`: dev omits `peer_stats: true`; schema default is `False` (`config/schema.py:58`), so the overlay expresses it as an explicit `peer_stats: false` — no key-removal semantics needed.
- `ui`: dev adds `display_fields.facility` (nested-dict addition); `navigation` identical.
- `policy_rules`: one scalar differs inside the nested list (`thresholds.max_billed_amount` 5000 → 100).

Every difference is expressible with deep-merged mappings + wholesale list replacement.

## Design

### 1. Merge semantics (ADR content)

- **Mappings deep-merge**: overlay keys win; recursion into nested dicts.
- **Lists and scalars replace wholesale.** No list-merge-by-key: heterogeneous keying (`id`, `name`, positional) would complicate the algebra, and the measured diff shows the only list-level change is a single small block (`policy_rules`) the overlay simply restates. The ADR records this trade-off: an overlay touching any element of a list restates the whole list.
- **Explicit `null` sets the field to `None`** (Pydantic validation still applies afterward); absence falls through to base/schema defaults. No removal operator.
- **Algebra**: right-biased recursive dict union with list/scalar replacement is associative — `(base ⊕ A) ⊕ B == base ⊕ (A ⊕ B)` — and `{}` is the identity. The AC's property-based tests (via `hypothesis`, added to the backend `[dev]` extra — new dev dependency) prove associativity, empty-overlay identity, and list-replacement.
- Field-value precedence: base ← overlay₁ ← overlay₂ … (declared order, last wins). Path-resolution precedence is untouched: explicit `path` arg > active-pack pointer (`load_active_config`) > `CHILI_CONFIG_PATH`.

### 2. Overlay files are not packs

- Overlays live in a new **`backend/config/overlays/`** directory. The config router's pack catalog iterates `config/defaults/` (`api/routers/config.py:83,437`), so overlays never appear as loadable packs.
- Required key `overlay_for: <domain.name>` (the guard above). Missing `overlay_for` in an overlay file is a `ConfigLoadError` (an overlay must always declare its base).
- **Unknown-top-level-key rejection**: any key not in `DomainConfig.model_fields` ∪ `{overlay_for}` raises `ConfigLoadError` naming the key (catches `embeddngs:`-style typos).

### 3. Loader integration

- New `backend/config/overlay.py`:
  - `merge_config_layers(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]` — the pure merge.
  - `apply_overlays(base_data: dict[str, Any], overlay_paths: list[Path]) -> dict[str, Any]` — reads/parses each overlay (reusing the loader's YAML/JSON parsing), enforces `overlay_for` + unknown-key rules, skips-with-warning on domain mismatch, merges in order.
- `load_config` reads `CHILI_CONFIG_OVERLAY_PATH` (comma-separated paths, applied in declared order) after parsing the base and **before** `_validate`. Applies on every load path — explicit path, env, and the pointer-following `load_active_config` (which delegates to `load_config`) — safe because of the `overlay_for` guard.
- The loader's overlay-related `TODO(production)` line is retired (secrets-resolution and hot-reload TODO clauses remain).

### 4. The refactor

- `medicare_fraud_dev.yaml` moves from `config/defaults/` to `config/overlays/` rewritten as a minimal overlay: `overlay_for: medicare_fraud`, the nine dev infra/knob sections, `capabilities: {peer_stats: false}`, `ui.display_fields.facility`, and the restated `policy_rules` block.
- The AC's "~80% line reduction" is **measured and reported honestly** in the commit/story annotation — list-replace forces the `policy_rules` restatement, so the realistic outcome is nearer 60–70%; the ADR documents why.
- `backend/tests/api/test_config_router.py`'s `MEDICARE_DEV_YAML` fixture (currently pointing at `defaults/`) updates to whatever role that test actually needs (a second full pack fixture or the new overlay path — decided at implementation by reading the test's subject; do not weaken it).
- **Follow-up recorded, out of scope**: `medicare_fraud_cms_desynpuf.yaml` — the live dev pack — duplicates the same infra sections and is a natural base+overlay candidate later; likewise the compose files keep pointing at full packs (no compose change in this story).

### 5. ADR + docs

- First ADR in the repo: `docs/architecture/decisions/0001-config-overlay-merge-semantics.md` (new directory) — context, decision (deep-merge + list-replace + `overlay_for` skip guard), consequences (list restatement trade-off, no removal semantics).
- `backend/README.md`: overlay model with a worked example (`CHILI_CONFIG_PATH` + `CHILI_CONFIG_OVERLAY_PATH` boot). `backend/config/README.md` and `docs/architecture.md` (§ domain-config model) updated; CLAUDE.md/copilot-instructions only if contradicted.

### 6. Testing

- `backend/tests/config/test_overlay.py`:
  - **Property-based (hypothesis)**: associativity over generated nested dicts, empty-overlay identity, list-replacement (overlay list wins wholesale).
  - **Example-based**: nested dict merge, explicit-null override, unknown-top-level-key rejection (named key in error), `overlay_for` match applies / mismatch skips with warning (caplog) / missing raises, comma-separated stacking order (last wins), overlay applied before validation (invalid merged config still fails `model_validate`).
- Loader tests: `CHILI_CONFIG_OVERLAY_PATH` honored via env; empty/unset env is a no-op.
- Coverage ≥ 85% on `config/`; pyright --strict clean; ruff clean.
- **Live verification (in-sprint per sprint R-5)**: boot the API with `CHILI_CONFIG_PATH=config/defaults/medicare_fraud.yaml` + `CHILI_CONFIG_OVERLAY_PATH=config/overlays/medicare_fraud_dev.yaml` and confirm a dev knob (e.g. `monitoring.evaluation_interval_seconds`) is live via `GET /config/domain`; then hot-swap to the housing pack with the overlay still set and confirm the structured skip warning + clean housing config.

## Code touch points

`backend/config/overlay.py` (new), `backend/config/loader.py`, `backend/config/overlays/medicare_fraud_dev.yaml` (moved+rewritten; deleted from `defaults/`), `backend/tests/config/test_overlay.py` (new), `backend/tests/api/test_config_router.py`, `backend/pyproject.toml` (`hypothesis` in `[dev]`), `docs/architecture/decisions/0001-config-overlay-merge-semantics.md` (new), `backend/README.md`, `backend/config/README.md`, `docs/architecture.md`, `docs/backlog/config.md` (story closeout).
