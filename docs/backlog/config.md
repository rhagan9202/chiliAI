# config backlog

> **Scope:** Domain configuration schema, loader, defaults, validation, hot-reload, UI wizard, multi-env overrides, persistence, versioning.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story config.01: Reconcile DomainConfig schema with all module consumers

**ID:** config.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_multitenancy.02, analytics.08, analytics.09, analytics.14, analytics.23, llm.04, rag.03, records.08]
**Estimated size:** L

**As a** platform engineer,
**I need** every field declared in `DomainConfig` to be either consumed by a runtime code path or removed,
**so that** operators editing YAML are never silently ignored and `AlertsConfig.thresholds` stops being a phantom knob.

### Current State
- `DomainConfig` (`backend/config/schema.py:363-398`) exposes 17 sub-models; only `monitoring`, `analytics`, `records`, `auth`, `events`, `storage`, `graph`, `vectorstore`, `llm`, `embeddings`, `database`, `ui`, and `validation` are wired through DI in `backend/api/dependencies.py`.
- `IngestionConfig.chunking` is parsed and default configs declare it, but the API DI path still constructs `DocumentParsingOrchestrator` without passing `DomainConfig.ingestion.chunking`; `backend/ingestion/chunker.py` can build a configured chunker, but YAML values are not yet wired into the API/worker ingestion service.
- `RagConfig.top_k`/`expansion_depth`/`reranking_enabled` (`backend/config/schema.py:205-211`) are not threaded into `RagService`; `ServiceGraphContextExpander.__init__(depth=1)` is constructed with a literal default at `backend/api/_rag_bridges.py:152-157`.
- `AlertsConfig.thresholds` (`backend/config/schema.py:214-220`) is declared as `dict[str, dict[str, float]]` but `MonitoringService` reads only `MonitoringConfig.medium_threshold`/`high_threshold` (`backend/api/dependencies.py:605-613`); `grep -rn "AlertsConfig\|alerts.thresholds" backend/monitoring/` returns nothing.
- Auditor (Wave 1) flagged the per-entity `AlertsConfig.thresholds` dict as the canonical example of declared-but-unread config.

### Acceptance Criteria
- [ ] Open question "Where does authoritative threshold config live?" resolved in a short ADR committed under `docs/architecture/decisions/` (per-entity dict, flat scalars, or hybrid) and linked from this story.
- [ ] Losing side is removed from `backend/config/schema.py` (and `backend/config/defaults/*.yaml`) in one commit; surviving side is what every consumer reads.
- [ ] `IngestionConfig.chunking` is consumed by `backend/ingestion/service.py` (or the chunker constructed there) — `chunk_size`, `chunk_overlap`, `min_chunk_size`, and `strategy` round-trip from YAML to the chunker.
- [ ] `RagConfig.top_k`, `expansion_depth`, and `reranking_enabled` are consumed by `RagService` (or the bridges/factory that build it) instead of literal defaults at `backend/api/_rag_bridges.py:152-157` and `backend/rag/service_models.py:27`.
- [ ] A new unit test in `backend/tests/config/test_consumer_parity.py` iterates `DomainConfig`'s top-level fields and asserts each is referenced by at least one non-test module (importable map of field → consumer module).
- [ ] `backend/config/schema.py` docstring lists, per sub-model, the module(s) that read it.
- [ ] `backend/README.md` "Domain config" subsection updated to reflect the resolved threshold model.

### Verification
- `pytest backend/tests/config/ backend/tests/ingestion/ backend/tests/rag/ -q` green.
- Manual: edit `backend/config/defaults/medicare_fraud_dev.yaml` chunking + RAG values, restart API + worker, confirm the new values flow into ingestion (chunk sizes observed in `_chunks.size` metric/log) and into RAG (top_k visible in retrieval request).
- `pyright` clean on touched modules; coverage ≥ 85% on `backend/config/`.

### Code touch points
- `backend/config/schema.py` (modify — collapse `AlertsConfig.thresholds` ↔ `MonitoringConfig.*_threshold` per ADR)
- `backend/config/defaults/medicare_fraud.yaml`, `medicare_fraud_dev.yaml`, `medicare_fraud_cms_desynpuf.yaml`, `food_supply_chain.yaml` (modify)
- `backend/ingestion/service.py` (modify — read `ChunkingConfig`)
- `backend/api/_rag_bridges.py` (modify — drop literal `depth=1`)
- `backend/rag/service.py`, `backend/rag/service_models.py` (modify — honor `RagConfig`)
- `backend/api/dependencies.py` (modify — propagate `RagConfig` into `get_rag_service` factory once it exists)
- `backend/tests/config/test_consumer_parity.py` (new)
- `docs/architecture/decisions/<NNNN>-alerts-thresholds-shape.md` (new)
- `backend/README.md` (modify)

---

## Story config.02: Resolve *_env_var placeholders centrally in the loader

**ID:** config.02
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_plugins.11, _security.04, config.08, llm.13, rag.16]
**Estimated size:** M

**As a** platform engineer,
**I need** the config loader to resolve every declared `*_env_var` placeholder once at startup with a single error class and a structured audit trail,
**so that** missing secrets surface immediately, every adapter stops re-implementing `os.environ[name]`, and a secret-manager backend can plug in behind one seam.

### Current State
- `backend/config/loader.py:30-34` carries a `TODO(production)` for `${ENV_VAR}` placeholder resolution and unified env-var handling.
- Every adapter currently reads `os.environ[name]` itself (e.g. `backend/llm/factory.py`, `backend/graph/auth.py`, `backend/embeddings/adapters/openai_adapter.py`, `backend/storage/adapters/s3_adapter.py`); missing envs raise raw `KeyError` from disparate call sites.
- No startup-time validation that declared `*_env_var` names actually resolve.
- No audit log of which secret env-var names were consumed at boot.

### Acceptance Criteria
- [ ] New `SecretResolverProtocol` in `backend/config/secrets.py` with a default `EnvSecretResolver` implementation that reads `os.environ`.
- [ ] `load_config` collects every `*_env_var` field from the validated `DomainConfig` and resolves them once via the resolver, raising a single `ConfigLoadError` listing every missing/empty env name (not the first one).
- [ ] Adapters (`backend/llm/factory.py`, `backend/graph/auth.py`, `backend/embeddings/adapters/openai_adapter.py`, `backend/storage/adapters/s3_adapter.py`, others touching `*_env_var`) receive the resolved secret material (or a `SecretsBundle`) at construction and no longer call `os.environ` directly for declared env-var fields.
- [ ] A structured INFO log line is emitted once per startup listing the *names* (not values) of every env-var consumed.
- [ ] Unit tests cover (a) missing single env, (b) missing multiple envs aggregated into one `ConfigLoadError`, (c) empty-string env treated as missing, (d) successful resolution, (e) adapter-level absence of `os.environ` access via grep-style import check.
- [ ] `backend/config/schema.py` module docstring updated to point at the resolver as the single integration seam for future secret managers.

### Verification
- `pytest backend/tests/config/ backend/tests/llm/ backend/tests/graph/ backend/tests/storage/ backend/tests/embeddings/ -q` green.
- Manual: unset `OPENAI_API_KEY` with the openai LLM provider configured; API boot fails fast with a `ConfigLoadError` naming `OPENAI_API_KEY`.
- Coverage ≥ 85% on `backend/config/`.

### Code touch points
- `backend/config/secrets.py` (new — protocol + `EnvSecretResolver`)
- `backend/config/loader.py` (modify — invoke resolver after validation; aggregate errors)
- `backend/config/schema.py` (modify — docstring; introduce helper to enumerate `*_env_var` fields)
- `backend/llm/factory.py`, `backend/graph/auth.py`, `backend/embeddings/adapters/openai_adapter.py`, `backend/storage/adapters/s3_adapter.py` (modify — consume resolved secrets)
- `backend/tests/config/test_secrets.py` (new)

---

## Story config.03: Deepen validation depth and cross-field constraints

**ID:** config.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** [config.04, config.08]
**Estimated size:** M

**As a** platform engineer,
**I need** the loader to reject obviously broken adapter/UI/KB combinations at validation time,
**so that** runtime failures from `OllamaLlmClient` missing `base_url`, Neo4j missing `uri`, or `UiNavigationPageConfig.capability` referencing a non-existent flag never make it into a running process.

### Current State
- `_validate_cross_references` (`backend/config/schema.py:400-540`) covers duplicates, relationship endpoints, enum requirements, records-feed integrity, and the single vectorstore↔embeddings dimensions check.
- Missing constraints (each is a documented runtime crash today):
  - `LlmConfig.provider="ollama"` requires `base_url` (`backend/config/schema.py:119-122`); `OllamaLlmClient` fails at first call otherwise.
  - `GraphDbConfig.backend="neo4j"` requires `uri` and `auth_env_var` (`backend/config/schema.py:97-103`).
  - `ObjectStoreConfig.backend in {"s3","minio"}` requires `bucket` and `credentials_env_var` (`backend/config/schema.py:140-147`).
  - `DatabaseConfig.backend="postgres"` requires the env named by `dsn_env_var` to be set (cross-edge to config.02).
  - `UiNavigationPageConfig.capability` (`backend/config/schema.py:229`) referencing only declared `CapabilitiesConfig` fields.
  - `UiDisplayFieldsConfig.title`/`subtitle`/`chips` (`backend/config/schema.py:238-243`) referencing real `EntityDefinition.properties` names.
  - `default_reference_kb_id` (`backend/config/schema.py:391-398`) referencing an existing KB at startup (per open question, deferred to readiness probe — see ACs).

### Acceptance Criteria
- [ ] `_validate_cross_references` (or a co-located `_validate_backend_requirements`) raises actionable errors aggregating every missing constraint listed above; one config with N violations produces one `ConfigLoadError` listing all N.
- [ ] `UiNavigationPageConfig.capability` is validated against `CapabilitiesConfig.model_fields` keys; unknown capability ⇒ error naming the page and the unknown capability.
- [ ] `UiDisplayFieldsConfig` title/subtitle/chip properties validated against the corresponding `EntityDefinition.properties` keys.
- [ ] `default_reference_kb_id` deferred to a startup readiness probe (does **not** load-time validate) — implemented as a check in `/readyz` (cross-edge `api.19`); a comment on the field links the deferred check.
- [ ] Per-violation unit tests in `backend/tests/config/test_schema_cross_validation.py` covering each new constraint plus an aggregate-error-message test.
- [ ] `backend/config/defaults/*.yaml` all pass the strengthened validator (regression test loads each).

### Verification
- `pytest backend/tests/config/ -q` green; coverage ≥ 85% on `backend/config/`.
- Manual: craft a YAML with ollama provider missing `base_url`; loader rejects with the new error.
- `pyright` clean.

### Code touch points
- `backend/config/schema.py` (modify — extend `_validate_cross_references`)
- `backend/config/defaults/*.yaml` (audit; fix any new violations)
- `backend/tests/config/test_schema_cross_validation.py` (new/modify)

---

## Story config.04: Support base + environment overlay layering for domain config

**ID:** config.04
**Status:** done
**Prerequisites:** [config.03]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** overlay layering itself has NOT landed — no `overlay.py`, no `CHILI_CONFIG_OVERLAY_PATH`, no merge ADR. What did land is adjacent switch ergonomics (d466249): `CHILI_CONFIG_PATH` is parameterized in both compose files (api + worker in lockstep, medicare default) and `make dev-domain DOMAIN=<pack>` selects a whole pack. Whole-pack selection reduces but does not remove the duplication this story targets; the ACs below all remain open. — **superseded 2026-07-15, see "Current State (shipped)" below.**
**Unblocks:** [agent.05, agent.10, config.08, ingestion.08, ingestion.09, ingestion.13, ingestion.15]
**Estimated size:** M
**Done:** 2026-07-15 · BL-044 (Sprint 2026-27) · `feat/sprint-2026-27-config-overlay`

**As a** platform engineer,
**I need** a documented overlay strategy that lets `medicare_fraud_dev.yaml` declare only its dev-specific overrides instead of duplicating the base file,
**so that** environment drift between dev/staging/prod is localized and reviewable.

### Current State (shipped)
- `docs/architecture/decisions/0001-config-overlay-merge-semantics.md` (the repo's first ADR) records the merge semantics: mappings deep-merge with overlay keys winning recursively; lists and scalars replace wholesale; explicit `null` sets a field to `None`; no key-removal operator.
- `backend/config/overlay.py` ships the pure merge (`merge_config_layers`) and the guarded application (`apply_overlays(..., base_path, parse)`, `OverlayError`, public `known_top_level_keys()`). Every overlay must declare `overlay_for: <pack filename stem>`; a mismatch against the base pack's filename stem skips the overlay with a structured warning (product-owner ruling 2026-07-15, hot-swap safety) rather than failing the boot; a missing `overlay_for` or an unknown top-level key raises `OverlayError` → `ConfigLoadError`. The guard was re-scoped from `domain.name` to the pack filename stem by a later product-owner re-ruling (also 2026-07-15, applied 2026-07-16 in the sprint 2026-27 fix-later burn-down) after packs sharing a `domain.name` (`medicare_fraud.yaml` / `medicare_fraud_cms_desynpuf.yaml`) were found to silently share an overlay; see [ADR 0001's amendment](../architecture/decisions/0001-config-overlay-merge-semantics.md#amendment-2026-07-15--guard-re-scoped-from-domain-to-pack).
- `backend/config/loader.py`'s `load_config` reads `CHILI_CONFIG_OVERLAY_PATH` (comma-separated, declared order, last wins) and applies the overlay stack after parsing, before `model_validate` — on every load path (explicit `path`, plain env, and `load_active_config`'s pointer resolution, since it delegates to `load_config`). The loader's overlay-related `TODO(production)` line is retired.
- `backend/config/overlays/medicare_fraud_dev.yaml` replaces the retired `backend/config/defaults/medicare_fraud_dev.yaml` full pack: 115 lines vs. the old 284 (**59% reduction**, not the ~80% originally estimated — see annotations below).
- `backend/tests/config/test_overlay.py`: hypothesis property tests for associativity-on-type-stable-stacks, empty-overlay identity, and list-replacement, plus example-based tests for nested-dict merge, explicit-`null` override, unknown-key rejection, `overlay_for` match/mismatch(caplog)/missing, comma-separated stacking order, and a golden equivalence test (`test_medicare_dev_overlay_reproduces_old_full_config`) proving `medicare_fraud.yaml ⊕ overlays/medicare_fraud_dev.yaml` reproduces the retired full dev file exactly (modulo the documented `peer_stats` exception), loaded from a checked-in fixture (`backend/tests/config/fixtures/medicare_fraud_dev_full_snapshot.yaml`) rather than git history, since CI's checkout is shallow. `backend/tests/config/test_loader.py` covers the `CHILI_CONFIG_OVERLAY_PATH` env wiring (set/unset/comma-separated). `backend/tests/api/test_config_router.py`'s dev-config fixture now points at the overlay path.
- `backend/README.md`, `backend/config/README.md`, and `docs/architecture.md` §9.2 document the overlay model, directory layout, and the extended path/overlay precedence line.

### Acceptance Criteria
- [x] ADR under `docs/architecture/decisions/` records the merge semantics (deep-merge with list-replace **or** list-merge-by-key — pick one, document the tradeoff). Deep-merge + wholesale list-replace chosen (ADR 0001).
- [x] `backend/config/overlay.py` ships the merge function with property-based tests covering associativity (base ⊕ A ⊕ B === base ⊕ (A ⊕ B)), idempotency of empty overlay, and list-handling per ADR. **Deviation (Task-1 review, amended in the spec and ADR 0001):** unrestricted associativity is false — a middle layer that collapses a mapping to a scalar makes grouping order observable. Associativity is property-tested only on *type-stable* layer stacks; a deterministic test (`test_merge_type_flip_is_left_to_right_not_associative`) pins the type-flip case to left-to-right (application-order) semantics instead.
- [x] `load_config` accepts `CHILI_CONFIG_PATH` (base, required) and `CHILI_CONFIG_OVERLAY_PATH` (optional, comma-separated for stack-of-overlays); overlays applied in declared order before `model_validate`.
- [x] `medicare_fraud_dev.yaml` refactored to a minimal overlay on top of `medicare_fraud.yaml` (delete duplicated entity/relationship/records blocks); diff in the same commit demonstrates ~80% line reduction. **Deviation:** measured reduction is **59%** (284 → 115 lines), not ~80% — see annotation (1) below.
- [x] `backend/config/loader.py` rejects an overlay that introduces a top-level key not defined on `DomainConfig` (catch typos like `embeddngs:`). Implemented in `apply_overlays` via `known_top_level_keys()` (`DomainConfig.model_fields` ∪ `{overlay_for}`); the loader surfaces it as `ConfigLoadError`.
- [x] `backend/README.md` documents the overlay model with a worked example. Also documented in `backend/config/README.md` and `docs/architecture.md` §9.2 per Task 5.

### Story annotations (2026-07-15)
1. **Measured reduction is 59%, not the AC's ~80% estimate.** List-replace semantics (ADR 0001) force the overlay to restate the whole `policy_rules` list even though only one scalar threshold (`max_billed_amount`) differs from the base — that single restated block accounts for most of the shortfall against the original ~80% estimate. The ADR documents this as a deliberate trade-off against the added complexity of keyed list-merging.
2. **The overlay lives in `backend/config/overlays/`, not `backend/config/defaults/`.** This keeps the pack catalog (`api/routers/config.py`, which iterates `defaults/` for discovery/switch) from ever listing a partial, non-standalone-loadable config as a switchable pack.
3. ~~**`config/` is not yet in pyright's strict `include` scope** (`backend/pyproject.toml`'s `tool.pyright.include` has no `config` entry). `backend/config/overlay.py` and `backend/tests/config/test_overlay.py` are independently strict-clean (`pyright config/overlay.py tests/config/test_overlay.py` → 0 errors), but a pre-existing strict error exists elsewhere in the package at `backend/config/schema.py:682` (`reportUnknownVariableType` on `ScorecardsConfig.templates`). Hardening the whole `config` package into the strict include scope is follow-up work, not part of this story (also recorded in `docs/project/planning/sprints/2026-27.md`'s fix-later notes).~~ **RESOLVED 2026-07-16** (sprint 2026-27 fix-later burn-down, Task 7): `config` and `tests/config` added to `tool.pyright.include`; the `ScorecardsConfig.templates` error fixed (a `default_factory=list` vs `default_factory=lambda: []` bidirectional-inference gap, not a missing annotation); `config/overlay.py`/`config/loader.py`'s `dict[str, Any]` replaced with `pydantic.JsonValue`. Bare `pyright` is 0 errors project-wide.

### Verification
- `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -m "not integration" -q` green; `backend/tests/config/test_overlay.py` covers the merge/guard/golden-equivalence surface described above.
- `pyright` clean (bare, repo-wide gate); `ruff check --no-cache .` clean.
- Manual: boot API with `CHILI_CONFIG_PATH=backend/config/defaults/medicare_fraud.yaml CHILI_CONFIG_OVERLAY_PATH=backend/config/overlays/medicare_fraud_dev.yaml` and confirm dev-specific knobs (e.g. `monitoring.evaluation_interval_seconds`) are applied; then hot-swap to another pack with the overlay env var still set and confirm the structured skip warning + clean base config. **Live-stack verification passed 2026-07-15**: merged config served with the overlay-only `monitoring` section live via `GET /config/domain`; hot-swap to the housing pack with the overlay env still set produced the structured skip warning and clean base config (no medicare rule leakage); `/config/packs` no longer lists the retired dev pseudo-pack. The dev compose gained a `CHILI_CONFIG_OVERLAY_PATH` passthrough (api+worker) in the verification pass so the documented workflow is exercisable in-stack.

### Code touch points
- `backend/config/overlay.py` (new)
- `backend/config/loader.py` (modify)
- `backend/config/overlays/medicare_fraud_dev.yaml` (new; moved+rewritten from `backend/config/defaults/medicare_fraud_dev.yaml`, which is deleted)
- `backend/tests/config/test_overlay.py` (new)
- `backend/tests/config/fixtures/medicare_fraud_dev_full_snapshot.yaml` (new; checked-in golden fixture)
- `backend/tests/config/test_loader.py` (modify — env overlay wiring)
- `backend/tests/api/test_config_router.py` (modify — dev-config fixture points at the overlay)
- `backend/pyproject.toml` (modify — `hypothesis` added to `[dev]`)
- `docs/architecture/decisions/0001-config-overlay-merge-semantics.md` (new)
- `backend/README.md`, `backend/config/README.md`, `docs/architecture.md` (modify)

---

## Story config.05: Add config hot-reload with atomic downstream cache invalidation

**ID:** config.05
**Status:** planned
_Note (2026-08-08, supersedes the 2026-07-12 note): `feat/domain-packs-and-config-manager` **merged to prod on 2026-07-03** (`ff46080`) — nine days before that note called it unmerged. Status stays `planned` for the other reason the old note gave: the prerequisites are themselves `planned` and the DAG invariant requires them `done` before `in-progress`. This story's title promises an audit event, and `config.pack.apply` / `config.pack.switch` were added to the ledger on 2026-08-08 under `_security.06` — the write endpoints had been admin-gated and unaudited since they shipped._
**Prerequisites:** [config.07, events.04]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** the core hot-reload mechanics landed as domain hot-swap (524b5bb, 648f413, 410a34c, a8573e5, 5b6646c):
- `reset_domain_config_caches()` exists in `backend/api/dependencies.py` with a monotonic swap-generation token (`get_config_generation`) and generation-guarded memoizers so an in-flight request sees a wholly-old or wholly-new dependency graph, never a torn one. Swap-once-success atomicity holds: validate (+ production auth guardrail) → persist pointer → reset caches → emit event; failure at any step leaves the prior config active.
- Reload trigger is admin-only `POST /config/apply` / `POST /config/switch` (not the `POST /config/reload` shape sketched here); a typed `ConfigUpdatedEvent` (`config.updated`) is published on the pre-swap event transport.
- Worker (`agent/coordinator.py`) consumes `config.updated` between drain iterations and rebuilds `WorkerDependencies` idempotently (redelivery-safe via `ConfigReloadState`).
Still open: the reload-posture ADR, the `config_reload_total` Prometheus counter (`_observability.04` cross-edge), and a reflection-based audit test asserting every config-keyed cache is covered by the reset helper. Constraint discovered during live verification: a pack must not change the event transport across a hot-swap (the `config.updated` event is published on the pre-swap transport; a transport change requires a restart).
**Unblocks:** [_plugins.11, analytics.29, config.08, ingestion.21, monitoring.03]
**Estimated size:** L

**As a** platform admin,
**I need** to reload a new domain config without restarting the API or worker processes,
**so that** threshold tweaks, prompt edits, and capability toggles take effect in seconds instead of after a deploy cycle.

### Current State
- `backend/config/loader.py:30-34` carries a `TODO(production)` for hot reload.
- `get_domain_config` is `@lru_cache(maxsize=1)` (`backend/api/dependencies.py:312-321`) and only cleared on `create_app()` (`backend/api/app.py:110-111`).
- Downstream factories (`get_graph_repository`, `get_vector_store`, `get_llm_service`, `get_embedder`, `get_monitoring_service`, `get_records_service`, `get_event_bus`, etc.) are also `@lru_cache(maxsize=1)` (`backend/api/dependencies.py:356-808`) and hold a config snapshot at construction.
- `backend/api/routers/config.py:18-21` calls out the missing `POST /config/reload`.
- Open question (Wave 1) on file-watcher vs. admin-trigger vs. both — must be locked.

### Acceptance Criteria
- [ ] ADR records the reload posture (admin-trigger only, file-watcher only, or both) and the atomicity guarantee (`load+validate+swap-once-success` — failed reload leaves prior config active).
- [ ] `backend/api/dependencies.py` exposes a `reset_domain_config_caches()` helper that clears `get_domain_config` *and* every `@lru_cache` factory keyed off `DomainConfig`; an audit test in `backend/tests/api/test_dependencies.py` asserts the helper invalidates every cache discovered by reflection so new factories cannot drift.
- [ ] Worker (`backend/agent/coordinator.py`) subscribes to the `config.updated` event (cross-edge `events.04`) and reinitializes its config-dependent state on receipt.
- [ ] Reload is observable: structured log line + `config_reload_total{result="success|failure"}` Prometheus counter (cross-edge `_observability.04`).
- [ ] Unit tests: (a) successful reload swaps config and invalidates downstream caches; (b) failed reload (invalid YAML) preserves prior config; (c) concurrent reload requests are serialized; (d) worker handles the reload event without dropping in-flight work.
- [ ] `backend/README.md` documents the reload contract and operator runbook.

### Verification
- `pytest backend/tests/config/ backend/tests/api/test_dependencies.py backend/tests/agent/ -q` green.
- Manual: with API + worker running, edit `backend/config/defaults/medicare_fraud_dev.yaml`, POST to `/config/reload`, confirm the new value is reflected in `GET /config/domain` and in worker behavior without restart.
- Coverage ≥ 85% on `backend/config/` and `backend/api/dependencies.py` reload paths.

### Code touch points
- `backend/api/dependencies.py` (modify — `reset_domain_config_caches`)
- `backend/api/routers/config.py` (modify — already covered by config.07 for the route; this story owns invalidation semantics)
- `backend/config/loader.py` (modify — atomic load helper)
- `backend/agent/coordinator.py` (modify — consume `config.updated` event)
- `backend/tests/config/test_hot_reload.py` (new)
- `backend/tests/api/test_dependencies.py` (modify)
- `docs/architecture/decisions/<NNNN>-config-hot-reload-posture.md` (new)
- `backend/README.md` (modify)

---

## Story config.06: DomainConfigStore protocol + Postgres-backed persistence

**ID:** config.06
**Status:** planned
_Note (2026-08-08, supersedes the 2026-07-12 note): `feat/domain-packs-and-config-manager` **merged to prod on 2026-07-03** (`ff46080`) — nine days before that note called it unmerged. Status stays `planned` for the other reason the old note gave: the prerequisites are themselves `planned` and the DAG invariant requires them `done` before `in-progress`. This story's title promises an audit event, and `config.pack.apply` / `config.pack.switch` were added to the ledger on 2026-08-08 under `_security.06` — the write endpoints had been admin-gated and unaudited since they shipped._
**Prerequisites:** [database.02]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** a deliberately smaller persistence slice landed (524b5bb): `backend/config/store.py` is a file-backed **active-pack pointer store** (`data/config/active_pack.json` on the shared `chili-object-data` volume, atomic temp-file + `os.replace` writes, `read_active_pack`/`write_active_pack`/`clear_active_pack`/`resolve_config_path`). Boot-time resolution is pointer > `CHILI_CONFIG_PATH` env > error. It is intentionally not the versioned `DomainConfigStoreProtocol` this story specifies — it persists *which pack is active*, not config payloads/versions. All ACs below (protocol, filesystem/Postgres adapters, `domain_config` table + migration, version history, `CHILI_DOMAIN_CONFIG_STORE_BACKEND`) remain open; the pointer store should be reconciled into (or subsumed by) the versioned store when this story is executed.
**Unblocks:** [config.07, config.09, config.10, config.11, config.13]
**Estimated size:** L

**As a** platform engineer,
**I need** domain configuration to live in a versioned write-through store with both filesystem and Postgres adapters,
**so that** wizard saves, audit trails, tenant overrides, and migrations all have a persistent substrate.

### Current State
- Config lives only as a YAML file on disk loaded via `Path.read_text` (`backend/config/loader.py:60-66`).
- There is no `DomainConfigStore` protocol, no `domain_config` table, no version column, no `created_by` provenance.
- Open question (Wave 1) on file-as-bootstrap vs. file-as-one-shot-seed — must be locked.
- `database.02` (Postgres KB metadata adapter) establishes the repository pattern this story mirrors.

### Acceptance Criteria
- [ ] ADR locks the bootstrap model (file is bootstrap-only-when-DB-empty, or file remains the source-of-truth and DB is a projection — pick one).
- [ ] `backend/config/store.py` defines `DomainConfigStoreProtocol` with `load_active() -> StoredDomainConfig`, `save(payload: dict, *, change_note: str, actor_user_id: str | None) -> StoredDomainConfig`, `list_versions(limit: int) -> list[StoredDomainConfigSummary]`, and `load_version(version: int) -> StoredDomainConfig`.
- [ ] `FilesystemDomainConfigStore` and `PostgresDomainConfigStore` adapters implemented under `backend/config/adapters/`.
- [ ] Alembic migration adds `domain_config` table (`version int PK auto`, `created_at timestamptz`, `created_by text NULL`, `change_note text`, `payload jsonb NOT NULL`, `is_active bool`, unique partial index on `is_active=true`).
- [ ] Startup bootstrap path: if backend=postgres and table empty, seed the table from `CHILI_CONFIG_PATH` per the ADR.
- [ ] `get_domain_config` (`backend/api/dependencies.py:312`) routes through the store; the YAML-only path remains for the in-memory backend.
- [ ] `CHILI_DOMAIN_CONFIG_STORE_BACKEND={filesystem,postgres}` env knob with sensible default.
- [ ] Unit + integration tests cover load, save (writes a new version, flips `is_active`), list, load-by-version, and bootstrap-from-file.

### Verification
- `pytest backend/tests/config/ -q` green; coverage ≥ 85%.
- Manual: with `CHILI_DOMAIN_CONFIG_STORE_BACKEND=postgres` and a fresh Postgres, boot API; confirm row 1 in `domain_config` matches the YAML; POST a save (via config.07); confirm row 2 supersedes row 1.
- `pyright` clean; Alembic migration applies cleanly on a fresh DB.

### Code touch points
- `backend/config/store.py` (new — protocol)
- `backend/config/adapters/__init__.py`, `filesystem.py`, `postgres.py` (new)
- `backend/database/migrations/versions/<rev>_domain_config_table.py` (new)
- `backend/api/dependencies.py` (modify — route through store)
- `backend/config/loader.py` (modify — bootstrap helper)
- `backend/tests/config/test_store.py` (new)
- `backend/tests/config/adapters/test_postgres_store.py` (new, `@pytest.mark.integration`)
- `docs/architecture/decisions/<NNNN>-config-store-bootstrap.md` (new)

---

## Story config.07: Write API for domain config (`/config/domain` write endpoint with dry-run, ETag, audit event)

**ID:** config.07
**Status:** planned
_Note (2026-08-08, supersedes the 2026-07-12 note): `feat/domain-packs-and-config-manager` **merged to prod on 2026-07-03** (`ff46080`) — nine days before that note called it unmerged. Status stays `planned` for the other reason the old note gave: the prerequisites are themselves `planned` and the DAG invariant requires them `done` before `in-progress`. This story's title promises an audit event, and `config.pack.apply` / `config.pack.switch` were added to the ledger on 2026-08-08 under `_security.06` — the write endpoints had been admin-gated and unaudited since they shipped._
**Prerequisites:** [config.06, _security.11]
**Progress note (2026-07-03, feat/domain-packs-and-config-manager):** a pack-management API landed (a8573e5, 5b6646c) covering much of this story's intent with a pack-file (not payload-write) shape:
- `GET /config/packs` (discovery + active-pack state), `POST /config/validate` (dry-run over a pack reference **or** inline content, structured field-level `ConfigValidationIssue` list), `POST /config/apply` (re-validate + hot-swap the on-disk pack, defaulting to the active one), `POST /config/switch` (activate a different pack) — all `require_role("admin")`, DTOs in `backend/api/config_models.py`, contracts regenerated.
- Successful swaps publish a typed `ConfigUpdatedEvent` (this story's AC) and the production auth guardrail (`api.dependencies.enforce_production_guardrail`) runs against the candidate pack in step 1, so a swap can never disable auth under `CHILI_ENV=staging|production`.
- Pack references are confined to allow-listed config directories (no arbitrary path reads).
Still open: a true write endpoint accepting a full `DomainConfig` payload and persisting it (there is deliberately **no raw pack read/write endpoint yet** — the UI validates edited content inline but apply re-applies the on-disk file), ETag/If-Match concurrency, versioned persistence via config.06, and the audit trail (config.09). The `TODO(production)` framing at the top of `backend/api/routers/config.py` is superseded by the shipped routes.
**Unblocks:** [api.25, config.05, config.09, config.13, monitoring.05]
**Estimated size:** M

**As a** platform admin,
**I need** an authenticated write endpoint that validates a new domain config, returns precise validation errors, supports a dry-run, and emits an audit/event signal on commit,
**so that** the wizard (config.08) can round-trip drafts and operators have a programmatic CLI path.

### Current State
- The router now serves reads (`/config/domain`, `/config/features`, `/config/domain/schema`, viewer-gated) **and** admin-gated pack management (`GET /config/packs`, `POST /config/validate|apply|switch`) — see progress note above.
- `require_role("admin")` is attached to the pack-management routes; a payload-write endpoint with ETag/audit remains unbuilt.
- `api.25` opens the admin write surface umbrella; `_security.11` audits and tightens the admin-tier RBAC; `config.06` provides the store.

### Acceptance Criteria
- [ ] The `/config/domain` write endpoint (HTTP method finalized by API design decision) accepts a full `DomainConfig` payload, validates via `DomainConfig.model_validate`, re-raises `ConfigLoadError` with the same shape as the loader, persists via `DomainConfigStoreProtocol.save`, and returns `{version, etag, change_note, actor_user_id, applied_at}`.
- [ ] Query param `?validate_only=true` runs validation but does not persist; returns 200 with `{ok: true, version: null}` on success or 422 with the structured error list.
- [ ] `If-Match: <etag>` header required on writes; mismatched ETag returns 412 Precondition Failed (etag = stable hash of active version + payload).
- [ ] `require_role("admin")` enforced on writes; `require_role("viewer")` continues to gate reads.
- [ ] Successful commit publishes a typed `ConfigUpdatedEvent` on the event bus (consumed by `config.05` for cache invalidation and by `config.09` for audit).
- [ ] OpenAPI `operation_id`s set (`update_domain_config`, `validate_domain_config`); request/response models declared.
- [ ] Tests cover happy path, validation failure (422), unauthorized (401/403), ETag mismatch (412), dry-run, and event-publication side effect.
- [ ] Removes the `TODO(production)` block at `backend/api/routers/config.py:18-21`.

### Verification
- `pytest backend/tests/api/test_config_router.py -q` green; coverage ≥ 85% on `backend/api/routers/config.py`.
- Manual: call the `/config/domain` write endpoint with a config tweak as admin, observe the `ConfigUpdatedEvent` in the worker log (relies on config.05), confirm `GET /config/domain` reflects the new payload.

### Code touch points
- `backend/api/routers/config.py` (modify — add write + validate endpoint)
- `backend/api/contracts.py` (modify — `DomainConfigUpdateRequest`, `DomainConfigUpdateResponse`)
- `backend/events/types.py` (modify — add `ConfigUpdatedEvent`; coordinate with events.04)
- `backend/config/store.py` (modify — ETag computation helper)
- `backend/tests/api/test_config_router.py` (new/modify)

---

## Story config.08: Define config UI wizard schemas and draft model

**ID:** config.08
**Status:** planned
**Prerequisites:** [config.02, config.03, config.04, config.05]
**Unblocks:** [config.14]
**Estimated size:** L

### Narrative
As an operator,
I want the configuration wizard to have typed schemas and a draft model,
so that UI work can safely validate planned configuration changes before saving.

### Current State
Configuration endpoints and files exist, but wizard-specific schema slices and draft lifecycle are not defined.

### Acceptance Criteria
- [ ] Wizard v1 scope is documented for environment, storage, graph, LLM, auth, ingestion, and monitoring sections.
- [ ] Backend exposes typed schema metadata for each wizard section.
- [ ] Draft model captures edited values separately from active configuration.
- [ ] Draft validation reports field-level errors without applying changes.

### Verification
- [ ] Unit tests cover schema metadata and draft validation for representative sections.
- [ ] Invalid drafts return structured errors suitable for frontend rendering.

### Code touch points
- `backend/app/config/**`
- `backend/app/api/**`
- `backend/tests/**`
- `docs/wiki/modules/config.md`

---
## Story config.09: Config change audit log and version history

**ID:** config.09
**Status:** planned
**Prerequisites:** [config.06, config.07, _security.06]
**Unblocks:** []
**Estimated size:** M

**As a** compliance reviewer,
**I need** every domain-config change recorded with `(actor_user_id, tenant_id, version, change_note, diff, applied_at)` and an admin UI surface for viewing history and rolling back,
**so that** I can answer "who changed the alert thresholds last quarter?" and revert a bad change in one click.

### Current State
- `backend/api/routers/config.py:21` carries a `TODO(production)` for "change audit logging".
- No `AuditLog` model, no audit router, no config-change records — `grep -rn "audit_log" backend/` returns zero.
- `_security.06` introduces the durable audit log substrate this story extends.
- Cross-edge to `database.md` for the audit table migration (covered there).

### Acceptance Criteria
- [ ] Each successful `/config/domain` write (config.07) emits an audit record with `(actor_user_id, tenant_id, prev_version, new_version, change_note, diff_json, applied_at, source: "api"|"cli")`; failed saves are NOT audited (validation errors are not changes).
- [ ] `GET /config/domain/versions?limit=N` (admin) lists recent versions with summaries.
- [ ] `GET /config/domain/versions/{version}` returns full payload + audit row.
- [ ] `POST /config/domain/rollback/{version}` creates a *new* version whose payload equals the named historical version; original audit row preserved (rollback is a forward operation, never a rewrite — keeps DAG monotonic).
- [ ] Wizard (config.08) exposes a "History" view and a "Roll back to this version" action gated on admin role.
- [ ] Tests cover audit row creation, listing, fetching by version, rollback creating a new version, and tenant scoping (audit row records `tenant_id` from the request context).

### Verification
- `pytest backend/tests/api/test_config_router.py backend/tests/config/ -q` green; coverage ≥ 85%.
- Manual: submit a config change through the `/config/domain` write endpoint, then `GET /config/domain/versions`, confirm the audit row carries the right actor and diff.

### Code touch points
- `backend/api/routers/config.py` (modify — add versions + rollback routes)
- `backend/config/store.py` (modify — `list_versions`, `load_version` already in config.06; add `record_audit_entry`)
- `backend/config/audit.py` (new — diff computation, audit record DTO)
- `chili_app/src/components/config/HistoryPanel.tsx` (new)
- `backend/tests/api/test_config_router.py`, `backend/tests/config/test_audit.py` (new/modify)

---

## Story config.10: Schema versioning and forward migration

**ID:** config.10
**Status:** planned
**Prerequisites:** [config.06]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** stored configs to be tagged with a `schema_version` and migrated forward when sub-models gain/rename/remove fields,
**so that** a config saved under v1.0 still loads cleanly after a code upgrade to v1.1 and unknown future versions fail with a clear error.

### Current State
- `DomainConfig.schema_version: str = "1.0"` (`backend/config/schema.py:370`) is present but never read by the loader and never asserted.
- Nothing migrates a stored config when a sub-model changes.
- Open question (Wave 1) on automatic-vs-admin-triggered migration — must be locked.
- `config.06` provides the persistent store this story migrates.

### Acceptance Criteria
- [ ] ADR locks the migration trigger (automatic at startup, admin-triggered via `POST /config/migrate`, or both).
- [ ] `backend/config/migrations/` package with `__init__.py` exposing an ordered registry and a `migrate_to_current(payload: dict, declared_version: str) -> dict` entry point.
- [ ] First migration `v1_0_to_v1_1.py` (no-op scaffolding) committed as the template; tests use a fixture migration to exercise the chain.
- [ ] `load_config` (and `DomainConfigStore.load_active`) invoke `migrate_to_current` before `model_validate`; mismatched declared version vs. registry head triggers a migration (or aborts per ADR).
- [ ] Unknown / future `schema_version` raises `ConfigLoadError` with a clear "this config was written for a newer chiliAI version" message.
- [ ] When the trigger is automatic, every migration is logged structurally (`from`, `to`, `transformations[]`) and emits a Prometheus counter.
- [ ] Tests cover (a) up-to-date config no-op path, (b) one-step migration, (c) multi-step chain, (d) unknown-future-version refusal, (e) corrupt payload error surface.

### Verification
- `pytest backend/tests/config/test_migrations.py -q` green; coverage ≥ 85%.
- Manual: seed `domain_config` table with a payload carrying `schema_version="1.0"`, advance the registry head to "1.1" via a fixture, reload — confirm migration applied (or admin trigger required per ADR).

### Code touch points
- `backend/config/migrations/__init__.py`, `v1_0_to_v1_1.py` (new)
- `backend/config/loader.py` (modify — invoke `migrate_to_current`)
- `backend/config/store.py` (modify — call migration on `load_active`)
- `backend/tests/config/test_migrations.py` (new)
- `docs/architecture/decisions/<NNNN>-config-schema-migration-trigger.md` (new)

---

## Story config.11: Tenant-scoped configuration loading and per-tenant overrides

**ID:** config.11
**Status:** planned
**Prerequisites:** [config.06, _multitenancy.02, _multitenancy.04]
**Unblocks:** [_multitenancy.13]
**Estimated size:** L

**As a** platform operator,
**I need** the config loader, DI cache, and write API to be tenant-aware so that tenants can override a safe subset of fields on top of platform defaults,
**so that** multi-tenant deployments do not share a single global config.

### Current State
- `backend/config/loader.py:20` loads a single global config from `CHILI_CONFIG_PATH`; no tenant axis on loader, DI cache, API routes, or wizard.
- `get_domain_config` is `@lru_cache(maxsize=1)` (`backend/api/dependencies.py:312`) — keying on tenant requires reworking the cache.
- `_multitenancy.02` introduces the tenant binding on `DomainConfig`; `_multitenancy.13` covers per-tenant loading from the multitenancy side; `_multitenancy.04` adds the request-scoped tenant DI context — this story is the config-module side of all three.
- Open question (Wave 1) on tenant-override scope (wholesale vs. subset) — must be locked in the multitenancy ADR.

### Acceptance Criteria
- [ ] `DomainConfigStoreProtocol.load_active(tenant_id: TenantId | None)` extended; Postgres adapter scopes by tenant; filesystem adapter rejects tenant != None with a clear error.
- [ ] Per-tenant overlay schema documented: the safe-subset of fields a tenant may override (`capabilities`, `alerts.thresholds`, `ui.display_fields`, `ui.navigation`, `rag.*`, others per multitenancy ADR); platform-level fields (`graph`, `vectorstore`, `embeddings`, `database`, `events`, `storage`, `auth`) remain platform-controlled.
- [ ] `get_domain_config(tenant_id)` keyed on tenant; cache implemented as a bounded `dict[TenantId, DomainConfig]` with explicit `reset_for_tenant` and `reset_all` operations; config.05 reload contract honored per-tenant.
- [ ] The `/config/domain` write endpoint (config.07) and audit log (config.09) carry tenant context; tenant admins can only write their own overlay, platform admins can write base.
- [ ] Tests cover (a) two tenants get two distinct configs, (b) tenant overlay merge applies only to whitelisted fields, (c) platform-tier write affects every tenant base, (d) reload invalidates the right tenant cache only, (e) cross-tenant leakage prevented (tenant A cannot read tenant B's overlay).

### Verification
- `pytest backend/tests/config/test_tenant_loading.py -q` green; coverage ≥ 85%.
- Manual: with two tenants seeded, hit `GET /config/domain` as each user, confirm distinct payloads.

### Code touch points
- `backend/config/store.py`, `backend/config/adapters/postgres.py` (modify)
- `backend/api/dependencies.py` (modify — per-tenant cache)
- `backend/config/overlay.py` (modify — restrict to safe-subset when tenant overlay)
- `backend/api/routers/config.py` (modify — tenant context)
- `backend/tests/config/test_tenant_loading.py` (new)

---

## Story config.12: Plugin-config escape hatch in DomainConfig

**ID:** config.12
**Status:** planned
**Prerequisites:** [_plugins.01, _plugins.03]
**Unblocks:** []
**Estimated size:** M

**As a** plugin author,
**I need** a typed `plugins: dict[str, PluginConfig]` field on `DomainConfig` with `enabled`, `version_constraint`, and provider-validated `settings`,
**so that** my plugin can declare and persist its own configuration without forking the schema or living on the side.

### Current State
- `CapabilitiesConfig` (`backend/config/schema.py:49-57`) is a closed scalar-bool model; `AnalyticsConfig` (`backend/config/schema.py:189-202`) has no extension point.
- No `plugins:` field anywhere on `DomainConfig`; a third party has nowhere to declare or persist its own configuration.
- `_plugins.01` defines the plugin SPI; `_plugins.03` defines the manifest format (including `config_schema`); this story exposes the config surface those depend on.
- Open question (Wave 1) on validation timing (block startup on plugin discovery vs. lazy validate) — must be locked.

### Acceptance Criteria
- [ ] ADR locks plugin-config validation timing.
- [ ] `backend/config/schema.py` adds `PluginConfig` (`enabled: bool`, `version_constraint: str`, `settings: dict[str, Any]`) and `DomainConfig.plugins: dict[str, PluginConfig] = Field(default_factory=dict)`.
- [ ] Loader-stage validation: per-plugin `settings` is validated against the plugin's declared `config_schema` (resolved from the plugin registry per `_plugins.03`); unknown plugin keys yield a clear "no plugin registered for id 'X'" error (per ADR — either at load time or lazily on first plugin call).
- [ ] `version_constraint` parsed as a PEP 440 spec; the plugin's reported version must satisfy it or the plugin is refused at boot.
- [ ] Tests cover (a) valid plugin config, (b) unknown plugin id, (c) settings schema mismatch, (d) version constraint mismatch, (e) plugin disabled (settings still validated for round-trip).
- [ ] `default_factory=dict` ensures legacy configs without a `plugins:` block still load unchanged.

### Verification
- `pytest backend/tests/config/test_plugin_config.py -q` green; coverage ≥ 85%.
- Manual: install the worked-example plugin from `_plugins.07`, set `plugins.example-noop.enabled=true`, reload, confirm the plugin runs.

### Code touch points
- `backend/config/schema.py` (modify — add `PluginConfig` and `plugins` field)
- `backend/config/loader.py` or new `backend/config/plugin_validation.py` (validate against registry)
- `backend/tests/config/test_plugin_config.py` (new)
- `docs/architecture/decisions/<NNNN>-plugin-config-validation-timing.md` (new)

---

## Story config.13: Domain-pack export / import (config + sample data bundle)

**ID:** config.13
**Status:** planned
**Prerequisites:** [config.06, config.07, ingestion.05, records.02]
**Unblocks:** [knowledgebases.10]
**Estimated size:** L

**As a** domain author,
**I need** a `.chiliai-pack` bundle format that bundles a domain's config YAML with optional sample documents and sample records feeds, plus `GET /config/export` and `POST /config/import` routes (and a CLI wrapper),
**so that** I can share a custom domain or restore one without copy-pasting YAML and reconstructing sample data by hand.

### Current State
- There is no export/import path today; sharing a domain means copying YAML by hand and reconstructing sample data.
- Existing precedent: `medicare_fraud_cms_desynpuf.yaml` ships alongside `tools/sample_data/build_tennessee_subset.py` — the pack format formalizes this pairing.
- Open question (Wave 1) on pack format (zip vs. directory layout) — must be locked.
- `ingestion.05` (storage-then-publish outbox) and `records.02` (row-level idempotency) underpin atomic install of sample data without partial-state failures.

### Acceptance Criteria
- [ ] ADR locks the bundle shape (single `.chiliai-pack` zip with a defined manifest, or a directory convention).
- [ ] Bundle manifest schema documented: `format_version`, `domain.name`, `chiliai_min_version`, `config_path` (in-bundle), optional `sample_documents/` listing per-KB, optional `sample_records/` listing per-feed, optional `signature` (deferred to `_security.md` for trust model).
- [ ] `GET /config/export?include_samples=false|true` (admin) returns the bundle as `application/zip` (or tarball per ADR) with the active config and, optionally, a sample-data snapshot.
- [ ] `POST /config/import` (admin) accepts the bundle, validates the manifest, validates the embedded config via the loader, and atomically installs (config → store via `config.07`; sample documents → ingestion pipeline via `ingestion.05`; sample records → records pipeline via `records.02`); on any step failure, the import rolls back (no half-installed domain).
- [ ] Conflict policy on existing domain name: `?on_conflict=reject|new_version|replace` (default `reject`) — `replace` is a hard write that creates a new config version with `change_note="domain pack import: <pack_id>"`.
- [ ] `tools/domain_pack.py` CLI wrapper: `build`, `inspect`, `install`, `extract` subcommands hitting the same code paths for offline use.
- [ ] Tests cover bundle build, inspect, install happy path, install rollback on bad sample doc, conflict policies, and signature-absent (informational warning, not error, per the deferred trust-model note).

### Verification
- `pytest backend/tests/config/test_domain_pack.py -q` green; coverage ≥ 85%.
- Manual: `python tools/domain_pack.py build --domain medicare_fraud_cms_desynpuf --include-samples /tmp/mf.chiliai-pack`; `python tools/domain_pack.py install /tmp/mf.chiliai-pack`; confirm config + sample data both land.

### Code touch points
- `backend/config/domain_pack.py` (new — build/inspect/install/extract library)
- `backend/api/routers/config.py` (modify — `GET /config/export`, `POST /config/import`)
- `tools/domain_pack.py` (new — CLI wrapper)
- `backend/tests/config/test_domain_pack.py` (new)
- `docs/architecture/decisions/<NNNN>-domain-pack-format.md` (new)
- `backend/README.md` (modify)

## Story config.14: Save and apply validated configuration drafts

**ID:** config.14
**Status:** planned
**Prerequisites:** [config.08]
**Unblocks:** [config.15, frontend.25]
**Estimated size:** L

### Narrative
As an operator,
I want validated configuration drafts to be saved and applied through backend APIs,
so that configuration changes have a controlled lifecycle.

### Acceptance Criteria
- [ ] Backend saves draft configuration changes with author, timestamp, and validation status.
- [ ] Apply endpoint writes validated config through the existing configuration persistence path.
- [ ] API returns a structured diff between active configuration and draft values.
- [ ] Invalid drafts cannot be applied.

### Verification
- [ ] API tests cover draft save, diff, invalid apply rejection, and successful apply.
- [ ] Config persistence tests confirm applied values are reloadable.

### Code touch points
- `backend/app/config/**`
- `backend/app/api/**`
- `backend/tests/**`

---

## Story config.15: Add config wizard admin audit and E2E coverage

**ID:** config.15
**Status:** planned
**Prerequisites:** [config.14]
**Unblocks:** [frontend.03, frontend.26, monitoring.07]
**Estimated size:** M

### Narrative
As an administrator,
I want configuration wizard changes to be audited and covered end to end,
so that operational changes can be reviewed and trusted.

### Acceptance Criteria
- [ ] Applying a draft emits an audit/event record with changed sections and actor identity.
- [ ] Admin authorization is enforced for save and apply operations.
- [ ] E2E coverage exercises validation, save, diff, and apply flows.

### Verification
- [ ] Authorization tests reject non-admin config mutation.
- [ ] Browser/API E2E test proves a valid draft can be applied and reloaded.

### Code touch points
- `backend/app/config/**`
- `backend/app/events/**`
- `tests/e2e/**`

---
