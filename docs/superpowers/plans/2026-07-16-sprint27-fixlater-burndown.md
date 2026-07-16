# Sprint 2026-27 Fix-Later Burn-Down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the recorded sprint 2026-27 fix-later items — graph adapter parity, pack-scoped overlays (PO re-ruling), the auth tail, records silent-drop surfacing, config pyright hardening, and the scorecards charter — per `docs/superpowers/specs/2026-07-15-sprint27-fixlater-burndown-design.md`.

**Architecture:** Seven independent tasks across five modules. Graph: Neo4j relationship `metadata_json` + `updated_at` parity + duplicate-id fold + polish. Config: `overlay_for` matches the base pack's filename stem; `/config/validate` gains `with_overlays`. Auth: `jwks_cache_seconds` wired, malformed-IdP-response 400, churn counter. Records: row-suppression counter + additive receipt field. Plus the config package enters pyright strict scope and the scorecards module backlog is chartered.

**Tech Stack:** Python 3.12, Pydantic v2, Neo4j (schemaless — no migration), FastAPI, prometheus_client, OpenAPI codegen.

## Global Constraints

- PO rulings (spec): pack-scoped `overlay_for` (filename stem match; ADR 0001 amended); counter + additive receipt field for records; all three optional items in scope.
- Explicitly skipped (spec §1, YAGNI): UNWIND unchanged-row filtering; in-memory adjacency-stale no-op marking. Do not implement them.
- Contract changes are ADDITIVE ONLY (`with_overlays` query param; `suppressed_existing_count` receipt field). Regen: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` (repo root) then `cd chili_app && npm run codegen:api`. Never hand-edit generated files.
- Gates from `/home/rdhagan92/chiliAI/backend`: targeted suites per task; full `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q`; bare `.venv/bin/pyright` 0 errors (after Task 7 this INCLUDES the config package); `.venv/bin/ruff check --no-cache .` clean.
- All commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Live verification (Task 7's final step) is RESERVED FOR THE CONTROLLER (no Docker in subagents).

---

### Task 1: Neo4j graph adapter parity — relationship metadata, updated_at, duplicate-id fold, polish

**Files:**
- Modify: `backend/graph/adapters/neo4j_adapter.py` (`upsert_entities`, `upsert_relationships`, `_read_existing_relationships`, `_relationship_row`, `_entity_row`, `_record_to_relationship`, `_read_existing_entity_ids` caller)
- Test: `backend/tests/graph/test_neo4j_adapter.py` (fake-driver + one live `-m integration` addition), `backend/tests/graph/test_in_memory_adapter.py` (mixed match/conflict test — adapter-agnostic semantics, add for in-memory too)

**Interfaces:**
- Consumes: existing `merge`/`version` semantics from BL-017 (shallow top-level merge; version bump only on effective change; metadata-only writes don't bump).
- Produces: Neo4j relationship rows carry `metadata_json`; reads deserialize it (absent property ⇒ `{}`); merge path shallow-merges relationship metadata; `updated_at` on effective writes = `payload.updated_at or utc_now()` computed Python-side for BOTH entities and relationships; duplicate ids within one batch fold sequentially (later occurrence merges onto the earlier's computed result, matching in-memory).

- [ ] **Step 1: Write the failing tests.** Fake-driver additions to `backend/tests/graph/test_neo4j_adapter.py` (reuse the module's queued-results harness and record helpers; assertions normative):

```python
def test_relationship_metadata_persists_and_merges(...) -> None:
    # queue: existence read (both endpoints found); existing-relationships read
    # returning a row with metadata_json='{"src": "doc1"}' and properties/version;
    # write echo.
    # upsert a relationship with metadata={"note": "x"} ->
    # write payload row must carry metadata_json == '{"note": "x", "src": "doc1"}'
    # merged-shallow (payload keys win), and version bump ONLY if properties/type/
    # weight changed (metadata alone does not bump — assert version unchanged).


def test_relationship_read_without_metadata_property_defaults_empty(...) -> None:
    # _record_to_relationship path: a fake relationship record LACKING metadata_json
    # deserializes with metadata == {} (legacy rows).


def test_updated_at_stamped_on_effective_entity_change(...) -> None:
    # existing row read; payload with updated_at=None and a changed property ->
    # write payload row's updated_at is a non-null isoformat string (utc_now stamped).


def test_intra_batch_duplicate_entity_id_folds_sequentially(...) -> None:
    # batch [ {id: e-1, properties: {a: 1}}, {id: e-1, properties: {b: 2}} ] against
    # empty store -> single write row for e-1 with properties_json containing BOTH
    # a and b (later occurrence merged onto earlier), version 1.


def test_mixed_match_conflict_batch_writes_nothing(...) -> None:
    # two existing entities at versions 1 and 3; batch upsert with expected_version=1:
    # first entity matches, second conflicts -> GraphVersionConflictError raised and
    # NO write query issued (only reads in driver.queries).
```

Also add the in-memory twin of the mixed match/conflict test to `test_in_memory_adapter.py` (both stored records unchanged afterward).

- [ ] **Step 2: Run to verify failure**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/graph -q -k "metadata or updated_at or folds or mixed"`
Expected: FAIL (no metadata_json handling; duplicate ids produce two rows; updated_at passthrough).

- [ ] **Step 3: Implement in `neo4j_adapter.py`.**
  1. `_relationship_row` gains `"metadata_json": _dump_json_property(relationship.metadata)`; the relationship write query SETs `relationship.metadata_json = row.metadata_json`; `_read_existing_relationships` selects `relationship.metadata_json AS metadata_json`; the merge path computes `new_metadata_json` exactly like the entity path (merge under `merge_properties`, replace otherwise) and metadata changes alone do NOT set `effective_change`.
  2. `_record_to_relationship`: read `metadata_json` via the module's existing `_load_json_mapping` helper with a `{}` default for absent properties (read the helper's contract first).
  3. `updated_at`: in both upserts' payload builds, on the UPDATE path set `row["updated_at"] = (entity.updated_at or utc_now()).isoformat()` (same for relationships); INSERT path keeps existing behavior. Import `utc_now` from `shared.utils` (check existing imports).
  4. Duplicate-id fold: in both upserts, build payloads through `payload_by_id: dict[str, dict[str, object]]` — when an id repeats, treat the previously computed row as the "existing" state for the second occurrence's merge/version computation (extract a small helper if it keeps the loop readable). Final `rows = list(payload_by_id.values())`.
  5. Polish: `missing_set = set(missing)` hoisted before the offending-relationships comprehension; entity update path passes precomputed JSON into `_entity_row` (add optional keyword args `properties_json: str | None = None, metadata_json: str | None = None` to `_entity_row`/`_relationship_row` rather than overwrite-after-build).

- [ ] **Step 4: Add the live integration test** (`@pytest.mark.integration`, reuse the live fixture):

```python
@pytest.mark.integration
def test_relationship_metadata_roundtrips_live(live_repository: Neo4jGraphRepository) -> None:
    kb = f"kb-meta-{uuid4()}"
    live_repository.upsert_entities(kb, [Entity(id="e-1", type="provider"), Entity(id="e-2", type="claim")])
    rel = Relationship(id="r-1", type="billed_for", source_id="e-2", target_id="e-1", metadata={"src": "doc1"})
    live_repository.upsert_relationships(kb, [rel])
    stored = live_repository.get_relationships(kb)[0]
    assert stored.metadata == {"src": "doc1"}
    live_repository.upsert_relationships(kb, [rel.model_copy(update={"metadata": {"extra": "y"}})])
    merged = live_repository.get_relationships(kb)[0]
    assert merged.metadata == {"src": "doc1", "extra": "y"}
    assert merged.version == 1  # metadata-only change: no bump
    live_repository.delete_knowledge_base(kb)
```

- [ ] **Step 5: Run tests + gates**

Run: `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/graph -q && .venv/bin/pytest tests/graph -q -m integration && .venv/bin/pyright && .venv/bin/ruff check --no-cache .`
Expected: all green (dev-stack Neo4j is running for the integration subset).

- [ ] **Step 6: Commit**

```bash
cd /home/rdhagan92/chiliAI
git add backend/graph backend/tests/graph
git commit -m "feat(graph): Neo4j relationship metadata + updated_at parity, duplicate-id fold, integrity-check polish

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: `GraphVersionConflictError` joins the coordinator's permanent-cause set

**Files:**
- Modify: `backend/agent/coordinator.py:1743-1760` (`handle_entities_validated` isolation block)
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Produces: the isolation check becomes `if not isinstance(cause, (GraphIntegrityError, GraphVersionConflictError)): raise`; the failure message and counter label derive from the cause (`error_class=type(cause).__name__`; message uses `str(cause)` for the version-conflict case, keeping the existing missing-endpoints wording for integrity errors).

- [ ] **Step 1: Write the failing test** — mirror `test_handle_entities_validated_isolates_integrity_failure`, but arm the conflict: build the validation report for doc-bad with an entity whose upsert will conflict (seed the entity at version 2, then `GraphBuildTask.upsert_options=GraphUpsertOptions(expected_version=1)`)… the handler builds the task internally without options, so instead: monkeypatch/stub the graph service's `upsert_task` for doc-bad to raise `BatchUpsertError` with `__cause__ = GraphVersionConflictError("e-1", 1, 2)` (follow the module's existing service-stubbing pattern). Assert: doc-bad → `DocumentsFailedEvent` with "version" in the message, `ingestion_documents_failed_total{stage="graph",error_class="GraphVersionConflictError"}` incremented, sibling doc processed.

- [ ] **Step 2: Run to verify failure** — `cd /home/rdhagan92/chiliAI/backend && .venv/bin/pytest tests/agent/test_coordinator.py -q -k version_conflict` → FAIL (re-raises today).

- [ ] **Step 3: Implement** — extend the isinstance check + derive the label/message:

```python
        except BatchUpsertError as exc:
            cause = exc.__cause__
            if not isinstance(cause, (GraphIntegrityError, GraphVersionConflictError)):
                raise
            if isinstance(cause, GraphIntegrityError):
                error_message = (
                    "Graph integrity violation: relationships reference "
                    f"missing entities {cause.missing_entity_ids} "
                    f"(relationships: {cause.relationship_ids})."
                )
            else:
                error_message = f"Graph version conflict: {cause}"
            ...
            ingestion_documents_failed_total.labels(
                stage="graph", error_class=type(cause).__name__
            ).inc()
```

(Adapt to the block's actual structure; import `GraphVersionConflictError` alongside the existing graph imports.)

- [ ] **Step 4: Run + gates** — `pytest tests/agent -q`, pyright, ruff → green.

- [ ] **Step 5: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator.py
git commit -m "feat(agent): version conflicts are permanent per-document failures at the graph stage

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Pack-scoped `overlay_for` + ADR amendment + meaningful known-keys test

**Files:**
- Modify: `backend/config/overlay.py` (`apply_overlays`), `backend/config/loader.py` (call site), `docs/architecture/decisions/0001-config-overlay-merge-semantics.md` (amendment section), `backend/config/README.md`, `backend/README.md` (guard description), `docs/auth`-unrelated guard mentions (grep `overlay_for`)
- Test: `backend/tests/config/test_overlay.py`, `backend/tests/config/test_loader.py`

**Interfaces:**
- Produces: `apply_overlays(base_data, overlay_paths, *, base_path: Path, parse: ...)` — guard compares `overlay[OVERLAY_FOR_KEY] != base_path.stem` (SKIP with warning naming both); `domain.name` no longer read. Loader passes `resolved` as `base_path`.

- [ ] **Step 1: Write/adjust the failing tests.** In `test_overlay.py`: all `apply_overlays` calls gain `base_path=` (pick paths whose stem matches/mismatches deliberately); the mismatch test asserts the warning names the stem; ADD `test_overlay_skips_same_domain_different_pack`: base data with `domain.name == "medicare_fraud"` but `base_path=Path(".../medicare_fraud_cms_desynpuf.yaml")` and overlay `overlay_for: medicare_fraud` → SKIPPED (this is the DE-SynPUF regression). In `test_loader.py`: env-overlay tests now match on the tmp base FILE's stem (write the overlay's `overlay_for` accordingly). Replace `test_apply_overlays_known_keys_track_domain_config` with:

```python
def test_shipped_dev_overlay_passes_unknown_key_guard_and_canary_fails(tmp_path: Path) -> None:
    """The unknown-key guard fires on realistic content: the SHIPPED dev overlay
    passes, and the same overlay plus one canary typo key is rejected naming it."""
    overlays_dir = Path(__file__).resolve().parent.parent.parent / "config" / "overlays"
    shipped = yaml.safe_load((overlays_dir / "medicare_fraud_dev.yaml").read_text())
    base = {"domain": {"name": "medicare_fraud"}}
    good = _write_yaml(tmp_path / "medicare_fraud_dev.yaml", shipped)
    apply_overlays(base, [good], base_path=Path("medicare_fraud.yaml"), parse=_parse_yaml)  # no raise
    shipped_bad = dict(shipped)
    shipped_bad["embeddngs"] = {"provider": "local"}
    bad = _write_yaml(tmp_path / "bad.yaml", shipped_bad)
    with pytest.raises(OverlayError, match="embeddngs"):
        apply_overlays(base, [bad], base_path=Path("medicare_fraud.yaml"), parse=_parse_yaml)
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/config -q` → FAIL (`base_path` unexpected).

- [ ] **Step 3: Implement.** `apply_overlays`: replace the `base_domain`/`base_name` extraction with `base_name = base_path.stem`; guard message: `"Skipping overlay %s: overlay_for=%r does not match base pack %r (pack-scoped guard, ADR 0001 amendment 2026-07-15)."`. Loader: `apply_overlays(data, overlay_paths, base_path=resolved, parse=_parse_config_file)`. Golden test: verify it still passes unchanged (base file IS `medicare_fraud.yaml`).

- [ ] **Step 4: ADR amendment.** Append to `docs/architecture/decisions/0001-config-overlay-merge-semantics.md`:

```markdown
## Amendment (2026-07-15) — guard re-scoped from domain to pack

The original decision matched `overlay_for` against the base config's
`domain.name`. In practice `medicare_fraud.yaml` and
`medicare_fraud_cms_desynpuf.yaml` share `domain.name: medicare_fraud`, so the
dev overlay silently applied to BOTH packs — including wholesale-replacing the
DE-SynPUF pack's three policy-rule packs with dev's two. Product-owner
re-ruling 2026-07-15: `overlay_for` now matches the base pack's **filename
stem**. Consequence: an overlay targets exactly one pack file; hot-swap safety
is preserved (mismatches still skip with a warning); overlays for a renamed
pack must be updated alongside the rename.
```

Update `backend/config/README.md` + `backend/README.md` guard prose (grep `domain.name` near overlay text).

- [ ] **Step 5: Run + gates** — `pytest tests/config tests/api -q`, pyright, ruff → green.

- [ ] **Step 6: Commit**

```bash
git add backend/config backend/tests/config docs/architecture backend/README.md
git commit -m "feat(config): overlay_for is pack-scoped (filename stem) per PO re-ruling; ADR 0001 amended

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `/config/validate` gains `with_overlays`

**Files:**
- Modify: `backend/api/routers/config.py:453-485` (`validate_pack`)
- Modify: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts` (regen)
- Test: `backend/tests/api/test_config_router.py`

**Interfaces:**
- Produces: `validate_pack(payload, with_overlays: bool = Query(default=False))` — when true AND the candidate came from a pack file (not inline `content`), apply the env overlays through the same `apply_overlays` path with that pack file as `base_path` before `DomainConfig.model_validate`; inline `content` + `with_overlays=true` ⇒ 422 (no base path to scope the guard against). Response model unchanged.

- [ ] **Step 1: Failing tests** (extend the router test class; monkeypatch `CHILI_CONFIG_OVERLAY_PATH`):

```python
def test_validate_with_overlays_applies_env_overlay(...) -> None:
    # overlay flips a knob that makes the merged config still-valid but observably
    # different: validate?with_overlays=true returns valid=True; and with an overlay
    # that injects an unknown key -> valid=False with the OverlayError message.


def test_validate_without_overlays_ignores_env(...) -> None:
    # same env set; with_overlays omitted -> overlay not applied (pack-only verdict).


def test_validate_with_overlays_rejects_inline_content(...) -> None:
    # payload.content given + with_overlays=true -> 422.
```

- [ ] **Step 2: Run to verify failure** → param unknown / behavior missing.

- [ ] **Step 3: Implement** in `validate_pack` (reuse `_overlay_paths_from_env` — import from `config.loader`; wrap `OverlayError` into a `ConfigValidationIssue(error_type="overlay_error")` `valid=False` response rather than an exception, mirroring the parse-error handling).

- [ ] **Step 4: Regen contracts** (repo root): export_openapi + `npm run codegen:api`; `git diff --stat chili_app` shows only generated files.

- [ ] **Step 5: Run + gates** — `pytest tests/api -q`, pyright, ruff, `cd chili_app && npm run lint && npm run test:run` → green.

- [ ] **Step 6: Commit**

```bash
git add backend/api backend/tests/api chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(api): /config/validate?with_overlays dry-runs the merged config

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Auth tail — `jwks_cache_seconds` wiring, malformed-IdP-response 400, churn metric

**Files:**
- Modify: `backend/api/middleware/auth.py` (`JwksCache.force_refresh` metric + `configure_jwks_cache`), `backend/api/app.py` (startup call), `backend/api/dependencies.py` (hot-swap reset path calls configure — find where config caches reset and hook there), `backend/api/routers/auth.py` (callback exchange error handling), `backend/shared/metrics.py` OR module-local counter (follow where `chili`-prefixed counters live — read `shared/metrics.py` first; auth is API-side so registering in `api/middleware/auth.py` on the default registry is acceptable — pick one and say why in the report)
- Test: `backend/tests/api/test_auth_middleware.py`, `backend/tests/api/test_auth_router.py`

**Interfaces:**
- Produces: `configure_jwks_cache(auth_config: AuthConfig | None) -> None` — sets the process-wide cache's `ttl_seconds` from `auth_config.jwks_cache_seconds` (no-op default 3600 when auth is None/disabled); called in `create_app` and on hot-swap. `chili_jwks_forced_refresh_total{outcome}` counter with `outcome ∈ {"refreshed", "throttled", "failed"}`: incremented in `force_refresh` (refreshed/throttled) and in `decode_token`'s refetch-exception handler (failed). Callback: `ValidationError` from `exchange_code`'s response parsing → 400 `"IdP token endpoint returned an invalid response."`.

- [ ] **Step 1: Failing tests**:

```python
def test_configure_jwks_cache_applies_config_ttl() -> None:
    # AuthConfig with jwks_cache_seconds=120 -> get_jwks_cache().ttl_seconds == 120;
    # configure with None -> resets to 3600.


def test_forced_refresh_counter_outcomes() -> None:
    # drive force_refresh through refreshed and throttled; drive decode_token's
    # refetch-failure; read the three counter samples from the default registry
    # (delta-based assertions — mirror how other counter tests sample REGISTRY).


def test_callback_idp_response_missing_access_token_is_400(...) -> None:
    # OIDC client double whose exchange_code raises pydantic.ValidationError
    # (build a real one via OidcTokens.model_validate({}) inside pytest.raises
    # capture, or monkeypatch exchange_code to raise it) -> callback 400 with
    # "invalid response" detail, no session cookie.
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** (metric increments inside `force_refresh`: `throttled` on the early-return branch, `refreshed` after a successful fetch; `failed` in `decode_token`'s `except` around `force_refresh`; keep `JwksCache` itself metric-free if that reads cleaner — incrementing at the call sites in `decode_token` is acceptable; state the choice in the report). `create_app`: after config load, `configure_jwks_cache(config.auth)`. Hot-swap: call it wherever `reset_config_caches`/the swap path re-derives config-driven singletons (read `api/dependencies.py:1839-1880` and `api/routers/config.py`'s apply path; wire at the point the new config is known).

- [ ] **Step 4: Run + gates** — `pytest tests/api -q`, pyright, ruff → green.

- [ ] **Step 5: Commit**

```bash
git add backend/api backend/tests/api
git commit -m "feat(auth): wire jwks_cache_seconds, 400 on malformed IdP token response, JWKS churn counter

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Records row-suppression counter + receipt field

**Files:**
- Modify: `backend/records/service.py:99-126`, `backend/records/service_models.py:23-38` (`RecordIngestReceipt`)
- Modify: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts` (regen)
- Test: `backend/tests/records/` (find the service tests; extend)

**Interfaces:**
- Produces: `RecordIngestReceipt.suppressed_existing_count: int = Field(default=0, ge=0)`; service computes `suppressed_existing = len(raw_records) - accepted` after `persist`, increments `ingestion_dedup_suppressed_total.labels(kind="record_row")` by that amount (only when > 0), and sets the receipt field. Batch-level `kind="record_batch"` unchanged.

- [ ] **Step 1: Failing tests**: push a batch, re-push a CHANGED-content row with the same `record_id` → receipt `accepted_count == 0`, `suppressed_existing_count == 1`, `duplicate is False`; counter sample for `kind="record_row"` increments by 1; a fresh row in the same push counts accepted and not suppressed (mixed batch: accepted 1, suppressed 1).

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** (import `ingestion_dedup_suppressed_total` from `shared.metrics` — it already exists with the `kind` label).

- [ ] **Step 4: Regen contracts**; frontend untouched otherwise.

- [ ] **Step 5: Run + gates** — `pytest tests/records tests/api -q`, pyright, ruff, `cd chili_app && npm run lint && npm run test:run` → green.

- [ ] **Step 6: Commit**

```bash
git add backend/records backend/tests/records backend/shared chili_app/openapi.json chili_app/src/lib/api/schema.ts
git commit -m "feat(records): surface row-level dedup suppression — counter + receipt field

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Config pyright hardening + scorecards charter + closeout (+ controller live pass)

**Files:**
- Modify: `backend/pyproject.toml:110-140` (`tool.pyright.include`: add `"config"` and `"tests/config"` entries in the list's existing style/order), `backend/config/schema.py:682` (+ whatever the scope expansion surfaces, anywhere in config/ and tests/config)
- Create: `docs/backlog/scorecards.md`
- Modify: `docs/project/planning/sprints/2026-27.md` (burn-down progress entry; fix-later lists updated: closed items marked, surviving tail restated), `docs/project/planning/backlog.md` (if any BL rows reference closed items), READMEs touched by earlier tasks re-checked for accuracy

- [ ] **Step 1: Expand pyright scope.** Add the include entries, run bare `.venv/bin/pyright`, and fix EVERY surfaced error with real types (start at `schema.py:682` — `ScorecardsConfig.templates` needs a concrete annotation; read the class and type it properly). Zero suppressions. Re-run until 0 errors.

- [ ] **Step 2: Charter `docs/backlog/scorecards.md`.** Follow an existing module backlog's header + story format exactly (`docs/backlog/records.md` is a good exemplar — match frontmatter/scope line/story structure so `scripts/backlog_consistency.py` parses it). Stories: scorecards.01 peer-stats depth hardening, scorecards.02 template versioning, scorecards.03 generation observability — each `planned` with honest Current State (read `backend/scorecards/` briefly to describe reality), AC checklists, and empty prerequisites unless a real one exists. Run `backend/.venv/bin/python scripts/backlog_consistency.py` (+ rollup rewrites) then `--check` → 0.

- [ ] **Step 3: Sprint-file closeout.** Progress entry "Fix-later burn-down (2026-07-16)": what closed (each item, one line), what survives (live-IdP verification, Auth0/Cognito templates, refresh rotation + back-channel logout, graph.03/04-scoped items, UNWIND filtering — explicitly re-listed). Mark the scorecards-charter carryover done.

- [ ] **Step 4: Full gates**

Run: `cd /home/rdhagan92/chiliAI/backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .` and `cd /home/rdhagan92/chiliAI/chili_app && npm run lint && npm run test:run`
Expected: full pass (config package now in-scope and clean), coverage ≥ 85% on touched packages.

- [ ] **Step 5: Live verification — RESERVED FOR THE CONTROLLER.** Against `make dev` (worker+api restarted onto the branch): (1) records push with a relationship-bearing feed → relationship `metadata` visible in Neo4j (cypher-shell); (2) with `CHILI_CONFIG_OVERLAY_PATH` set, boot on `medicare_fraud.yaml` → overlay applied; switch base to `medicare_fraud_cms_desynpuf.yaml` → overlay SKIPPED with the pack-scoped warning; (3) changed-content re-push of an existing record_id → receipt shows `suppressed_existing_count=1` and `ingestion_dedup_suppressed_total{kind="record_row"}` on `:8000/metrics`; (4) `/config/validate?with_overlays=true` vs `false` differ when an overlay is set.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/config docs/
git commit -m "chore(config,docs): config package enters pyright strict scope; scorecards backlog chartered; burn-down closeout

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-review notes (already applied)

- Spec coverage: §1→Tasks 1-2, §2→Tasks 3-4, §3→Task 5, §4→Task 6, §5→Task 7 Step 1, §6→Task 7 Steps 2-3, verification→each task + Task 7 Step 5. The YAGNI skips are restated in Global Constraints so no implementer adds them.
- Type consistency: `apply_overlays(..., base_path: Path, parse=...)` defined in Task 3 and consumed in Task 4; `configure_jwks_cache(AuthConfig | None)` internal to Task 5; `suppressed_existing_count` internal to Task 6.
- Test sketches follow the established convention: module fixtures are stand-ins, listed assertions/branches are mandatory.
- Tasks 3→4 are ordered (4 consumes 3's signature); everything else is independent.
