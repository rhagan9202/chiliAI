# ADR 0001 — Config overlay merge semantics

Date: 2026-07-15 · Status: accepted · Story: BL-044 / config.04

## Context

Environment configs duplicated the whole domain surface to flip a handful of
knobs (`medicare_fraud.yaml` vs `medicare_fraud_dev.yaml`). We need overlay
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

## Amendment (2026-07-15, Task-1 review)

The original design assumed the merge was associative without qualification.
Task 1's review found a counterexample: a middle layer that **collapses a
mapping to a scalar** discards structure that a different grouping order can
resurrect. Concretely, with `base={"k": {"z": 1}}`, `A={"k": 5}`,
`B={"k": {"w": 2}}`:

- `(base ⊕ A) ⊕ B` → `{"k": {"w": 2}}` (A's scalar wipes `z`, then B's dict
  replaces the scalar wholesale)
- `base ⊕ (A ⊕ B)` → `{"k": {"z": 1, "w": 2}}` (A ⊕ B first replaces the
  scalar with B's dict, so the later merge onto `base` deep-merges into `z`)

The two groupings disagree, so the merge is **not associative in general**.
The decision is narrowed accordingly:

- **Associativity holds only on type-stable layer stacks** — stacks where no
  layer changes a key's kind (mapping vs. non-mapping) relative to a layer
  that nests further into it. Real overlays target the fixed `DomainConfig`
  schema (a mapping's shape doesn't flip to a scalar between layers in
  practice), so type-stability holds for every overlay this story ships.
- The **type-flip case is pinned to left-to-right (application-order)
  semantics** — i.e. exactly what `merge_config_layers` naturally computes by
  folding overlays onto the base in declared order. There is no attempt to
  make grouping order irrelevant for type-flipping stacks; the deterministic
  test `test_merge_type_flip_is_left_to_right_not_associative` pins this
  boundary case so it cannot silently regress.
- Property tests (via `hypothesis`, a new `[dev]` dependency) **evidence**
  the algebra over generated type-stable stacks — they are not a proof of
  the unrestricted claim, only of the restricted (type-stable) one, plus
  empty-overlay identity and wholesale list replacement.

## Consequences

- The merge is associative with the empty overlay as identity, **restricted
  to type-stable layer stacks** (property-tested via hypothesis in
  `tests/config/test_overlay.py`); a middle layer that flips a key's kind
  between mapping and scalar is deliberately left-to-right (application
  order), not associative, and that boundary is pinned by a deterministic
  test rather than left implicit.
- An overlay touching one element of a list must restate the whole list —
  this held the dev-file reduction to 59% rather than ~80%.
- Overlays cannot delete keys; "off" states must be expressible as explicit
  values (e.g. `capabilities.peer_stats: false`).
