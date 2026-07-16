# Sprint 2026-27 fix-later burn-down (design)

> Status: approved by product owner 2026-07-15 (three rulings recorded below).
> Sprint: 2026-27 buffer. Scope: the recorded fix-later items from BL-017/BL-044/BL-023/BL-022 that are worth closing now, plus the twice-carried scorecards charter.

## Product-owner rulings (2026-07-15)

1. **Overlay guard becomes pack-scoped**: `overlay_for` matches the base pack's **filename stem** (e.g. `medicare_fraud` matches only `medicare_fraud.yaml`), replacing the domain.name match from ADR 0001 — the dev overlay no longer silently applies to `medicare_fraud_cms_desynpuf.yaml`. ADR 0001 gains an amendment section; the shipped overlay file's value already equals the stem, so it needs no edit.
2. **Optional inclusions all in**: config-package pyright hardening, `docs/backlog/scorecards.md` charter, `/config/validate` `with_overlays` param.
3. **Records silent-drop = counter + receipt field**: `ingestion_dedup_suppressed_total{kind="record_row"}` + additive `suppressed_existing_count` on the ingest receipt (contract regen; no frontend work).

## Work items

### 1. Graph adapter parity (BL-017 tail)

- **Relationship `metadata` persists in Neo4j**: `_relationship_row` gains `metadata_json` (written via `_dump_json_property`); `_read_existing_relationships` reads it; the merge path shallow-merges it exactly like entity metadata; `_record_to_relationship` deserializes it (missing property on legacy rows ⇒ `{}`). Metadata-only relationship changes write without bumping `version` (entity semantics).
- **`updated_at` parity**: on effective writes Neo4j computes `payload.updated_at or utc_now()` Python-side (matching in-memory); true no-ops keep whatever is stored.
- **Intra-batch duplicate-id fold** (defensive): the Neo4j entity/relationship payload builds fold duplicate ids through a running dict so a duplicated id compounds sequentially like in-memory (upstream dedup still guards; this closes the latent divergence).
- **`GraphVersionConflictError` → permanent cause**: `handle_entities_validated`'s isolation check accepts it alongside `GraphIntegrityError` (per-document `DocumentsFailedEvent`, `error_class="GraphVersionConflictError"`) — unreachable today (`expected_version` unarmed) but correct when armed.
- **Polish**: hoist `set(missing)` in the Neo4j integrity check; skip the double `json.dumps` on the entity update path (pass precomputed JSON into `_entity_row`); add the mixed match/conflict batch-atomicity test (first entity matches `expected_version`, second conflicts ⇒ neither written).
- **Explicitly skipped (YAGNI)**: filtering unchanged rows from the UNWIND payload; in-memory adjacency-stale no-op marking.

### 2. Overlay pack-scoping + validate param (BL-044 tail)

- `apply_overlays` gains the base path: signature becomes `apply_overlays(base_data, overlay_paths, *, base_path: Path, parse: ...)`; the guard compares `overlay[OVERLAY_FOR_KEY]` to `base_path.stem`; skip-warning wording updates ("does not match base pack '<stem>'"). `domain.name` no longer participates.
- ADR 0001 amendment section: the original domain-scoped ruling, the DE-SynPUF cross-pack surprise it produced, and the 2026-07-15 pack-scoped re-ruling. `backend/config/README.md`, `backend/README.md` worked example, and `docs/auth`-unrelated docs mentioning the guard update accordingly.
- Regression tests: dev overlay applies to `medicare_fraud.yaml`; SKIPS `medicare_fraud_cms_desynpuf.yaml` with the warning; golden equivalence test unaffected.
- `/config/validate` gains `with_overlays: bool = Query(default=False)` — when true, the dry run validates the merged config using the same overlay env/guard path as `load_config` (skipped overlays behave identically). Response shape unchanged; OpenAPI regen (query param is additive).
- The tautological known-keys test is replaced: load the SHIPPED dev overlay through `apply_overlays` against the real base with a canary unknown key injected — asserting the unknown-key guard actually fires on realistic content (a genuine drift guard), or an equivalent meaningful assertion.

### 3. Auth tail (BL-022)

- **Wire `jwks_cache_seconds`**: `configure_jwks_cache(auth_config)` sets the process-wide cache's `ttl_seconds` from `AuthConfig.jwks_cache_seconds`; called at app startup (`create_app`) and on config hot-swap (the existing cache-reset registry). Templates keep the field; the "dead config" note dies.
- **IdP 200 missing `access_token` ⇒ 400**: the callback wraps `exchange_code`'s response-shape `ValidationError` into the existing 400 path ("IdP token endpoint returned an invalid response") — no more 500.
- **Churn metric**: `chili_jwks_forced_refresh_total{outcome}` counter (`outcome="refreshed" | "throttled" | "failed"`) incremented inside `force_refresh` (and its failure path in `decode_token`), registered on the default registry like `shared/metrics.py` counters.

### 4. Records silent-drop surfacing (BL-015/BL-023 tail)

- `RawRecordStore.persist` already returns the inserted count; the service computes `suppressed_existing = len(raw_records) - inserted` (rows dropped by the `(kb, record_type, record_id)` conflict), increments `ingestion_dedup_suppressed_total{kind="record_row"}` by that amount, and the receipt gains `suppressed_existing_count: int = 0` (additive). Batch-level dedup (`kind="record_batch"`) is unchanged. Contract regen; no frontend edits.

### 5. Config-package pyright hardening

- Add `"config*"` and `tests/config` (per the include-list's existing conventions — read it) to `tool.pyright.include`; fix `schema.py:682` (`ScorecardsConfig.templates` unknown type) and every error the scope expansion surfaces, properly typed, zero suppressions.

### 6. Hygiene + closeout

- `docs/backlog/scorecards.md` charter: module header + story stubs for the known scorecards hardening ideas (peer-stats depth, template versioning — the items named when the carryover was recorded), following the module-backlog format so `backlog_consistency.py` accepts it.
- Sprint file: fix-later lists updated — items closed by this burn-down marked as such; remaining items (live-IdP verification, Auth0/Cognito templates, refresh rotation, back-channel logout, graph.03/04-scoped items, UNWIND filtering) restated as the surviving tail. Backlog consistency green.

## Verification

- Unit/integration per item (graph adapter tests incl. live Neo4j metadata round-trip integration test; overlay pack-scope tests; auth wiring/metric/400 tests; records suppression tests).
- **Live pass (controller-run)**: records push writes relationship metadata visible in Neo4j; dev overlay applies to `medicare_fraud` and SKIPS `cms_desynpuf` on the live stack; changed-content re-push shows `suppressed_existing_count` in the receipt and the `record_row` counter on `:8000/metrics`; `/config/validate?with_overlays=true` verdict differs from `false` when an overlay is set.
- Gates: full suite ≥ 85% on touched packages, bare pyright 0 (now including `config`), ruff clean, contracts regen, backlog consistency.

## Code touch points

`graph/adapters/neo4j_adapter.py`, `agent/coordinator.py`, `config/overlay.py` + `loader.py` + `api/routers/config.py`, `api/middleware/auth.py` + `api/app.py` + `api/dependencies.py` + `api/routers/auth.py`, `records/service.py` + `shared/metrics.py` + records service models, `backend/pyproject.toml` + `config/schema.py`, `docs/architecture/decisions/0001-*.md`, `docs/backlog/scorecards.md` (new), READMEs, `chili_app/openapi.json` + schema.ts (regen), planning docs.
