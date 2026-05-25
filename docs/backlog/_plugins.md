# _plugins backlog

> **Scope:** Plugin SPI definition, discovery, sandboxing, lifecycle, versioning, observability, first-party plugin migration, marketplace deferred to v2.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story _plugins.01: Define the v1 plugin SPI surface

**ID:** _plugins.01
**Status:** planned
**Prerequisites:** [shared.01, analytics.01, rag.01, records.01, monitoring.01]
**Unblocks:** []
**Estimated size:** L

**As a** chiliAI platform architect,
**I need** a written, code-anchored specification of the plugin SPI (which protocols third parties may implement, which seams are explicitly out of v1, and the FastAPI router-contribution shape),
**so that** every later plugin epic (discovery, manifest, lifecycle, testing harness, dogfood) has a single contract to build against and the SPI does not silently drift into adapter territory forbidden by `docs/architecture.md` §2.1.

### Current State
- No top-level `backend/plugins/` package; `grep -rn 'plugin' backend/` against source returns zero functional hits (only `.venv` deps).
- Existing protocol-shaped seams that the SPI must adopt rather than reinvent: `RiskScoringStrategyProtocol` at `backend/analytics/risk/protocols.py:25`, `DetectionStrategy` imported in `backend/analytics/timeseries/service.py:17`, and the service-level protocols (`RiskServiceProtocol` at `backend/analytics/risk/protocols.py:17`).
- All routers are hand-included in `backend/api/app.py:142-156`; no reserved prefix exists for plugin-contributed routers.
- `backend/pyproject.toml:22` already splits adapter dependencies into extras (`neo4j`, `qdrant`, `openai`, `anthropic`, `s3`, `sentence-transformers`) — informs which SPI surfaces are in scope vs. explicitly out.

### Acceptance Criteria
- [ ] New spec `docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` enumerates the in-scope SPI: analytics strategies (`RiskScoringStrategyProtocol`, `DetectionStrategy`, future `GnnScoringStrategyProtocol`), analytics services (`RiskServiceProtocol`, `GnnServiceProtocol`, `TimeseriesServiceProtocol`), custom monitoring rule protocol, custom RAG retriever protocol, custom record-feed mapper protocol.
- [ ] Spec explicitly lists out-of-scope-for-v1 seams: graph adapters, vector store adapters, LLM adapters, embeddings adapters, object-store adapters (these stay in-tree per `docs/architecture.md` §2.1).
- [ ] Spec defines the FastAPI router-contribution shape: plugins return zero-or-one `APIRouter` mounted by the host under the reserved prefix `/plugins/{plugin_id}`; host owns auth dependency wiring.
- [ ] Spec defines the agent.coordinator event-handler contribution shape: plugins may register zero-or-more `EventHandler` callables keyed by event type, dispatched by `agent/coordinator.py`.
- [ ] New file `backend/plugins/__init__.py` exporting an empty `PluginProtocol` placeholder and `SPI_VERSION: str = "1.0.0"` constant; module docstring links the spec.
- [ ] New file `backend/plugins/spi.py` declares `runtime_checkable` `PluginProtocol` with `manifest`, `startup(context)`, `shutdown()` methods; capability-specific protocols (`AnalyticsStrategyPlugin`, `MonitoringRulePlugin`, `RagRetrieverPlugin`, `RecordFeedMapperPlugin`, `RouterContributionPlugin`, `EventHandlerPlugin`) marked as Protocol mix-ins.
- [ ] `docs/architecture.md` §14.2 Plugin system row is updated with a back-link to `_plugins.md` and to the new SPI spec; no behavior change to other rows.

### Verification
- `pyright --strict` clean on `backend/plugins/`.
- `pytest backend/tests/plugins/test_spi_shape.py -q` passes; tests assert `SPI_VERSION` matches semver, every capability protocol is `runtime_checkable`, and the out-of-scope adapter protocols are not re-exported from `backend.plugins`.
- Spec doc rendered via `grep -c '^## ' docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` returns ≥ 8 sections (in-scope, out-of-scope, router shape, event-handler shape, manifest preview, lifecycle preview, sandboxing preview, versioning preview).
- Coverage ≥ 85% on `backend/plugins/` package (mostly type assertions at this stage).

### Code touch points
- `docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` (new)
- `backend/plugins/__init__.py` (new)
- `backend/plugins/spi.py` (new)
- `backend/tests/plugins/test_spi_shape.py` (new)
- `docs/architecture.md` (modify — §14.2 row only)

---

## Story _plugins.02: Implement plugin discovery and PluginRegistry

**ID:** _plugins.02
**Status:** planned
**Prerequisites:** [_plugins.01, config.01, api.01, agent.01]
**Unblocks:** []
**Estimated size:** XL

**As a** chiliAI platform operator,
**I need** a single mechanism that discovers installed plugins and exposes them to both `create_app()` and the agent coordinator,
**so that** third-party capabilities (analytics strategies, monitoring rules, RAG retrievers, record-feed mappers, contributed routers, event handlers) reach the runtime without hand-editing `backend/api/app.py` or `backend/api/dependencies.py`.

### Current State
- `backend/api/app.py:142-156` hand-includes 15 routers; there is no extension point.
- `backend/api/dependencies.py` hand-imports every adapter for DI; no registry of third-party-provided services exists.
- `backend/agent/coordinator.py` consumes Redis Streams events but has no plugin-supplied handler dispatch.
- No `$CHILI_PLUGIN_DIR` environment variable is read anywhere; no `importlib.metadata.entry_points(group="chiliai.plugins")` lookup exists in source.

### Acceptance Criteria
- [ ] Discovery mechanism decision (entry-points vs. `DomainConfig.plugins[].import_path` vs. directory scan) recorded in `docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` with rationale; v1 ships **at least** the entry-points path (`group="chiliai.plugins"`).
- [ ] New `backend/plugins/registry.py` exports `PluginRegistry` with `discover()`, `loaded_plugins -> Mapping[str, LoadedPlugin]`, `routers() -> list[APIRouter]`, `event_handlers() -> Mapping[str, list[Callable]]`, `services() -> Mapping[ProtocolType, object]`.
- [ ] `LoadedPlugin` dataclass carries `manifest`, `module`, `instance: PluginProtocol`, `state: PluginLifecycleState`.
- [ ] `backend/api/app.py` is refactored so the hand-included router block is preceded by `for router in plugin_registry.routers(): app.include_router(router, prefix=f"/plugins/{plugin_id}")`; no first-party router moved.
- [ ] `backend/agent/coordinator.py` consults `plugin_registry.event_handlers()` when dispatching events; ordering is first-party-then-plugin and documented.
- [ ] Discovery is one-shot at process startup; re-discovery requires restart (hot reload is _plugins.04's decision; v1 defaults to cold).
- [ ] Discovery failures (import error, malformed manifest, SPI-version mismatch) log structured errors via `structlog` tagged `plugin_id`, `failure_class` and exclude the failing plugin without crashing the host.
- [ ] Unit tests in `backend/tests/plugins/test_registry.py` cover: entry-point happy path, import-error isolation, malformed-manifest rejection, duplicate plugin-id detection, ordering of router/event-handler dispatch.

### Verification
- `pytest backend/tests/plugins/test_registry.py -q` green; coverage ≥ 85% on `backend/plugins/registry.py`.
- `pyright --strict backend/plugins backend/api/app.py backend/agent/coordinator.py` clean.
- Manual smoke: install a stub plugin via `pip install -e backend/tests/fixtures/sample_plugin`, start `uvicorn api.app:create_app --factory`, confirm `GET /plugins/sample/ping` returns 200 and structured log records contain `plugin_id=sample`.
- `make test` green end-to-end.

### Code touch points
- `backend/plugins/registry.py` (new)
- `backend/plugins/loaded_plugin.py` (new)
- `backend/api/app.py` (modify — extension hook only; first-party routers untouched)
- `backend/agent/coordinator.py` (modify — plugin event-handler dispatch)
- `backend/api/dependencies.py` (modify — expose plugin services through DI)
- `backend/tests/plugins/test_registry.py` (new)
- `backend/tests/fixtures/sample_plugin/` (new — stub plugin package)

---

## Story _plugins.03: Plugin manifest format and load-time validation

**ID:** _plugins.03
**Status:** planned
**Prerequisites:** [_plugins.01, _plugins.02, shared.02]
**Unblocks:** []
**Estimated size:** L

**As a** plugin author,
**I need** a documented manifest format that the host parses and validates before importing my plugin code,
**so that** missing capabilities, version mismatches, or missing permission declarations produce a clear error at install time, not a confusing crash deep in `agent.coordinator`.

### Current State
- No manifest schema exists; `backend/plugins/` is greenfield at the start of this story (created by _plugins.01).
- The `*_env_var` pattern in `backend/config/schema.py:7` is the existing convention for secret handling — plugin manifests must reuse it for any plugin-local secret references.
- `backend/pyproject.toml` has no `[tool.chiliai.plugin]` block today (this is where in-repo first-party plugins will declare their manifest per _plugins.09).

### Acceptance Criteria
- [ ] Manifest format decision recorded in the SPI spec: `chiliai_plugin.toml` at plugin package root **or** a `[tool.chiliai.plugin]` table in the plugin's `pyproject.toml`; both forms parsed identically.
- [ ] Required fields: `id` (RFC 1123 hostname-label), `name`, `version` (semver), `chiliai_api_version` (PEP 440 range), `capabilities` (list of SPI protocol names from _plugins.01), `entry_points` (mapping `capability -> "module:Class"`).
- [ ] Optional fields: `permissions` (list of declared scopes — see _plugins.05), `config_schema` (`"module:BaseModelSubclass"`), `description`, `homepage`, `license`.
- [ ] New `backend/plugins/manifest.py` exports `PluginManifest` (Pydantic v2 `BaseModel`) and `load_manifest(path: Path) -> PluginManifest`.
- [ ] `PluginRegistry.discover()` from _plugins.02 calls `load_manifest` **before** importing any plugin code; failures rendered as structured errors of shape `{plugin_id?, manifest_path, error_class, message, fix_hint}`.
- [ ] Defined failure modes each have a dedicated `ManifestValidationError` subclass: `ManifestMissingError`, `ManifestSyntaxError`, `ManifestSchemaError`, `ManifestCapabilityMismatchError`, `ManifestPermissionUnknownError`.
- [ ] `backend/tests/plugins/test_manifest.py` covers every failure mode plus the happy path; ≥ 1 fixture per error class.
- [ ] Plugin-author docs section in the SPI spec includes a minimal valid manifest example and a fully-populated example.

### Verification
- `pytest backend/tests/plugins/test_manifest.py -q` green; coverage ≥ 85% on `backend/plugins/manifest.py`.
- `pyright --strict backend/plugins/manifest.py` clean.
- Negative test: a stub plugin with a missing `chiliai_api_version` field is rejected at discovery, the error message includes `fix_hint="add chiliai_api_version: '>=1.0,<2.0'"`, and the host continues startup.
- Sample manifest in spec validates against `PluginManifest` via a doctest or fixture test.

### Code touch points
- `backend/plugins/manifest.py` (new)
- `backend/plugins/exceptions.py` (new)
- `backend/plugins/registry.py` (modify — call `load_manifest` first)
- `backend/tests/plugins/test_manifest.py` (new)
- `docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` (modify — manifest examples section)

---

## Story _plugins.04: Plugin lifecycle and admin endpoints

**ID:** _plugins.04
**Status:** planned
**Prerequisites:** [_plugins.02, _plugins.03, _security.07, api.02]
**Unblocks:** []
**Estimated size:** L

**As a** platform admin,
**I need** REST endpoints to list, enable, disable, and uninstall plugins, plus a defined lifecycle state machine and `startup`/`shutdown` hook contract,
**so that** operators can manage plugins through the same admin tooling as other platform features and a plugin's resource allocation is bounded and recoverable.

### Current State
- No `/plugins/*` router exists (see listing of `backend/api/routers/` — alerts, analytics, auth, cases, config, events, evidence, graph, investigation, knowledgebases, policy, rag, records, workflows, ws — none plugin-related).
- `PluginProtocol` from _plugins.01 declares `startup(context)` / `shutdown()` placeholders but has no caller.
- Admin RBAC role exists (added in _security.07 cycle); plugin endpoints must require it.

### Acceptance Criteria
- [ ] Lifecycle states defined as an enum in `backend/plugins/lifecycle.py`: `DISCOVERED → LOADED → ENABLED → DISABLED → UNLOADED`, plus terminal `FAILED` with `failure_reason`.
- [ ] Transition rules documented and asserted: `DISCOVERED→LOADED` requires manifest validation, `LOADED→ENABLED` invokes `startup(context)`, `ENABLED→DISABLED` invokes `shutdown()`, `DISABLED→UNLOADED` releases the module reference.
- [ ] Hot vs. cold enable/disable decision recorded in the SPI spec; v1 implements **cold** for capability/service contributions (config change + restart) and **hot** for router/event-handler enable/disable (per-process). Decision and rationale documented.
- [ ] New `backend/api/routers/plugins.py` exposes: `GET /plugins` (list with status), `GET /plugins/{id}` (detail incl. manifest, lifecycle state, last-error), `POST /plugins/{id}/enable`, `POST /plugins/{id}/disable`, `DELETE /plugins/{id}` (alias for disable+unload; does **not** uninstall the wheel).
- [ ] All endpoints guarded by `require_role("admin")`; default-deny audit (`assert_complete(app)` at `backend/api/app.py:161`) passes.
- [ ] `startup(context)` receives a `PluginContext` containing scoped logger/metrics/tracer (cross-edge _plugins.10), config (cross-edge _plugins.11), and capability-scoped clients (cross-edge _plugins.05).
- [ ] Endpoint contract tests in `backend/tests/api/test_plugins_router.py` cover happy paths, RBAC denial (401/403), unknown-plugin (404), state-transition errors (409).

### Verification
- `pytest backend/tests/api/test_plugins_router.py backend/tests/plugins/test_lifecycle.py -q` green; coverage ≥ 85% on `backend/api/routers/plugins.py` and `backend/plugins/lifecycle.py`.
- `pyright --strict` clean on touched files.
- Manual smoke against sample plugin from _plugins.02 fixture: `curl -H "Authorization: Bearer <admin>" :8000/plugins` returns the plugin; `POST /plugins/sample/disable` flips state and subsequent `GET /plugins/sample/ping` returns 404.
- `assert_complete(app)` from `backend/api/app.py:161` confirms every new route has an explicit auth dependency.

### Code touch points
- `backend/plugins/lifecycle.py` (new)
- `backend/plugins/context.py` (new — `PluginContext` dataclass)
- `backend/api/routers/plugins.py` (new)
- `backend/api/app.py` (modify — include `plugins_router`)
- `backend/api/dependencies.py` (modify — `get_plugin_registry` DI)
- `backend/tests/api/test_plugins_router.py` (new)
- `backend/tests/plugins/test_lifecycle.py` (new)

---

## Story _plugins.05: Capability-declaration enforcement at the SPI surface

**ID:** _plugins.05
**Status:** planned
**Prerequisites:** [_plugins.03, _plugins.04, _security.08]
**Unblocks:** []
**Estimated size:** XL

**As a** security-conscious operator,
**I need** every plugin's declared `permissions` to be enforced at the SPI surface (not just documented), so an analytics-strategy plugin that did not declare `event_publish` cannot publish events even if it tries,
**so that** the v1 trust model — "in-process plugins, capability-declared, enforced at the seam" — is a real boundary, not honor-system documentation. Subprocess/WASI isolation is explicitly deferred to a later epic.

### Current State
- No `permissions` field is enforced today; `_plugins.03` defines the manifest field but enforcement is this story.
- The graph adapter currently exposes full read/write surface (`backend/graph/protocols.py` style) — a plugin handed this object today could mutate freely.
- Outbound HTTP from any in-tree module is unbounded; there is no allowlist anywhere in the repo (`grep -rn 'http_outbound\|allowlist' backend/` returns no functional hits).
- `_security.08` (supply-chain / signing posture) is the cross-edge that decides whether `permissions` are advisory-only for unsigned plugins; this story consumes that decision.

### Acceptance Criteria
- [ ] Defined permission scopes (final list in SPI spec): `graph.read`, `graph.write`, `vector.read`, `vector.write`, `embeddings.invoke`, `llm.invoke`, `event.publish`, `event.subscribe`, `http.outbound`, `fs.read`, `fs.write`, `metrics.emit`.
- [ ] `PluginContext` (from _plugins.04) wraps capability clients in `ScopedClient` proxies that raise `PluginPermissionError` on any method outside declared scopes.
- [ ] `http.outbound` enforcement implemented as a `ScopedHttpClient` that consults a manifest-declared `outbound_allowlist: list[str]` (host patterns); requests outside the list raise `PluginPermissionError`.
- [ ] `event.publish` enforcement wraps the event bus so only declared event types are publishable; declared types are listed in the manifest under `event.publish.types`.
- [ ] No raw adapter object is leaked into `PluginContext` — every reachable client is scoped.
- [ ] Sandboxing-posture decision recorded in SPI spec: v1 is in-process capability enforcement; subprocess/WASI isolation tracked as a future epic with a cross-link to `_infra.md`.
- [ ] Tests in `backend/tests/plugins/test_capability_enforcement.py` cover one permitted-call and one denied-call per scope; tests assert `PluginPermissionError.scope` and `.attempted_action` fields.
- [ ] An end-to-end test loads a stub plugin that declares only `graph.read`, attempts `graph.write`, observes the denial, and confirms the host stays up.

### Verification
- `pytest backend/tests/plugins/test_capability_enforcement.py -q` green; coverage ≥ 85% on `backend/plugins/scoped_clients/`.
- `pyright --strict backend/plugins/scoped_clients/` clean.
- Negative-path verification: the fixture plugin in _plugins.02 is extended to attempt an undeclared `http.outbound` call; structured log emits `event="plugin_permission_denied" plugin_id=sample scope=http.outbound`.
- Security review checklist item added to `docs/security_checklist.md`.

### Code touch points
- `backend/plugins/scoped_clients/__init__.py` (new)
- `backend/plugins/scoped_clients/graph.py` (new)
- `backend/plugins/scoped_clients/vector.py` (new)
- `backend/plugins/scoped_clients/llm.py` (new)
- `backend/plugins/scoped_clients/events.py` (new)
- `backend/plugins/scoped_clients/http.py` (new)
- `backend/plugins/scoped_clients/fs.py` (new)
- `backend/plugins/exceptions.py` (modify — add `PluginPermissionError`)
- `backend/plugins/context.py` (modify — use scoped clients)
- `backend/plugins/manifest.py` (modify — add `outbound_allowlist`, `event.publish.types` fields)
- `backend/tests/plugins/test_capability_enforcement.py` (new)
- `docs/security_checklist.md` (modify — add plugin-capability section)

---

## Story _plugins.06: SPI versioning and compatibility matrix

**ID:** _plugins.06
**Status:** planned
**Prerequisites:** [_plugins.01, _plugins.03, _cicd.04]
**Unblocks:** []
**Estimated size:** M

**As a** plugin author and a platform release manager,
**I need** the host to publish its SPI version distinct from `backend.pyproject.toml:3 version`, reject plugins whose declared `chiliai_api_version` does not include the host SPI, and document the deprecation policy,
**so that** plugin authors have a stable contract independent of host bugfix releases and operators can predict which plugins survive a host upgrade.

### Current State
- `SPI_VERSION` constant is introduced as `"1.0.0"` in _plugins.01 but has no policy attached.
- `backend.pyproject.toml:3` carries `version = "0.1.0"` for the host backend; this is the wrong axis to version the SPI against.
- The `chiliai_api_version` manifest field is parsed by _plugins.03 but not yet enforced against the host SPI version.
- No compatibility matrix doc exists.

### Acceptance Criteria
- [ ] `backend/plugins/__init__.py` `SPI_VERSION` is documented as the source of truth, versioned by `MAJOR.MINOR.PATCH` semver with explicit semantics: MAJOR = breaking SPI change, MINOR = additive, PATCH = bugfix only.
- [ ] `PluginRegistry.discover()` rejects any plugin whose manifest `chiliai_api_version` PEP 440 range does not include `SPI_VERSION`; rejection produces a `ManifestSpiIncompatibleError` (subclass of `ManifestValidationError` from _plugins.03) with both versions in the message.
- [ ] Deprecation policy documented in SPI spec: any SPI-breaking change requires one full minor-version cycle with `DeprecationWarning` emitted from the deprecated SPI method at every call.
- [ ] New file `docs/plugins/compatibility_matrix.md` enumerates supported plugin `chiliai_api_version` ranges per host release; this file is updated by the _cicd.04 release workflow.
- [ ] Helper script `scripts/check_spi_version_bump.py` runs in CI: if `backend/plugins/spi.py` or any capability-protocol file changes in a PR, the PR must also bump `SPI_VERSION`; missing bump fails CI.
- [ ] Tests in `backend/tests/plugins/test_versioning.py` cover happy path, incompatible-range rejection, deprecation-warning emission, and the version-bump script.

### Verification
- `pytest backend/tests/plugins/test_versioning.py tests/scripts/test_check_spi_version_bump.py -q` green; coverage ≥ 85% on touched files.
- `pyright --strict` clean.
- `python scripts/check_spi_version_bump.py --check` exits 0 on a PR that bumps SPI and non-zero on a PR that does not.
- `docs/plugins/compatibility_matrix.md` lints clean with the consistency pass (no broken refs).

### Code touch points
- `backend/plugins/__init__.py` (modify — add `SPI_VERSION` docstring + policy)
- `backend/plugins/registry.py` (modify — incompatibility rejection)
- `backend/plugins/exceptions.py` (modify — `ManifestSpiIncompatibleError`)
- `docs/plugins/compatibility_matrix.md` (new)
- `docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` (modify — deprecation policy section)
- `scripts/check_spi_version_bump.py` (new)
- `tests/scripts/test_check_spi_version_bump.py` (new)
- `backend/tests/plugins/test_versioning.py` (new)

---

## Story _plugins.07: Plugin testing harness and `chiliai plugin verify` CLI

**ID:** _plugins.07
**Status:** planned
**Prerequisites:** [_plugins.02, _plugins.03, _plugins.05, shared.03]
**Unblocks:** []
**Estimated size:** L

**As a** third-party plugin author,
**I need** a published test harness that loads my plugin into an in-memory host with in-memory graph/vector/embedding/LLM/storage/event-bus adapters, plus a CLI command that runs manifest-conformance and SPI-contract tests,
**so that** I can validate compatibility without a running backend stack and CI can assert official plugins keep passing.

### Current State
- In-memory adapters exist per module (graph, vectorstore, llm, embeddings, storage, events) but are not exposed as a stable public surface for third-party consumption — they live in adapter-specific `in_memory.py` files (e.g. `backend/analytics/risk/adapters/in_memory.py`).
- No `chiliai` CLI exists today; entry-points group needs declaring in `backend/pyproject.toml`.
- No pytest fixture set for plugins.

### Acceptance Criteria
- [ ] New `backend/plugins/testing/` package exposes `PluginTestHarness` class: constructor takes a plugin module/path, builds an in-memory host with all in-memory adapters wired, calls discovery/load/enable, returns a context for assertions.
- [ ] Pytest fixtures published: `in_memory_plugin_host`, `loaded_plugin`, `enabled_plugin` — third-party plugins `pip install chili-backend[plugin-testing]` and use these directly.
- [ ] Manifest-conformance test suite: parametrized tests asserting every declared capability is reachable, declared permissions match actual SPI calls, `chiliai_api_version` covers host `SPI_VERSION`, manifest round-trips through `PluginManifest`.
- [ ] SPI-contract test suite: per-capability protocol conformance (e.g. analytics strategy plugin's `score()` returns `list[RiskFactor]`); leverages `runtime_checkable` Protocol from _plugins.01.
- [ ] New `chiliai` CLI entry point declared in `backend/pyproject.toml` `[project.scripts]`; first subcommand `chiliai plugin verify <path>` runs the harness + tests against the supplied plugin path.
- [ ] CLI documented in `docs/plugins/authoring_guide.md` with worked example; exit code 0 on pass, non-zero with structured-JSON output on failure.
- [ ] Worked-example plugin shipped under `backend/tests/fixtures/sample_plugin/` (extended from _plugins.02) implements a no-op `RiskScoringStrategy`, declares only `graph.read`, ships its own README and tests, passes `chiliai plugin verify`.
- [ ] Plugin-testing extras declared: `backend/pyproject.toml` `[project.optional-dependencies] plugin-testing = ["pytest>=8", "..."]`.

### Verification
- `pytest backend/tests/plugins/test_harness.py backend/tests/fixtures/sample_plugin/tests/ -q` green; coverage ≥ 85% on `backend/plugins/testing/`.
- `pyright --strict backend/plugins/testing/` clean.
- `chiliai plugin verify backend/tests/fixtures/sample_plugin` exits 0 and prints `PASS` per check.
- Negative test: temporarily delete a required manifest field on the sample plugin; `chiliai plugin verify` exits non-zero and emits a JSON payload naming the missing field.

### Code touch points
- `backend/plugins/testing/__init__.py` (new)
- `backend/plugins/testing/harness.py` (new)
- `backend/plugins/testing/fixtures.py` (new)
- `backend/plugins/testing/conformance.py` (new)
- `backend/plugins/cli.py` (new — `chiliai` CLI)
- `backend/pyproject.toml` (modify — `[project.scripts]`, `plugin-testing` extra)
- `backend/tests/fixtures/sample_plugin/` (modify — extend with full test suite)
- `backend/tests/plugins/test_harness.py` (new)
- `docs/plugins/authoring_guide.md` (new)

---

## Story _plugins.08: Plugin documentation contract and `chiliai plugin lint`

**ID:** _plugins.08
**Status:** planned
**Prerequisites:** [_plugins.07]
**Unblocks:** []
**Estimated size:** S

**As a** plugin consumer / operator,
**I need** every plugin to ship a minimum, predictable doc set (README with capability summary, declared permissions and rationale, config-schema description, version-compat statement; CHANGELOG keyed to plugin version),
**so that** I can install, audit, and operate a plugin without reading source code, and a `chiliai plugin lint` step in CI fails plugins that skip docs.

### Current State
- No plugin docs contract exists.
- `chiliai` CLI shipped by _plugins.07 has only one subcommand (`verify`); `lint` does not exist.
- The sample plugin from _plugins.07 has a minimal README but no formal contract.

### Acceptance Criteria
- [ ] Doc contract specified in `docs/plugins/authoring_guide.md` (extended from _plugins.07): required files `README.md`, `CHANGELOG.md`; required README sections `Capabilities`, `Installation`, `Declared permissions and rationale`, `Configuration`, `Compatibility`; optional `examples/` directory.
- [ ] `chiliai plugin lint <path>` subcommand checks: required files exist, required README sections present (heading match), `Declared permissions` lists every manifest permission with a non-empty rationale line, `CHANGELOG.md` has an entry for the current plugin version.
- [ ] Lint output uses the same structured-JSON failure shape as `chiliai plugin verify`.
- [ ] Template plugin repo scaffolded under `backend/tests/fixtures/template_plugin/`; passes both `verify` and `lint`. This is a working starting point an author can copy.
- [ ] `chiliai plugin lint` is part of the official-plugin CI workflow defined by the _cicd.md plugin-CI epic (cross-edge).
- [ ] Sample plugin from _plugins.07 updated to meet the new doc contract.

### Verification
- `pytest backend/tests/plugins/test_lint.py -q` green; coverage ≥ 85% on `backend/plugins/cli.py` (lint additions).
- `chiliai plugin lint backend/tests/fixtures/template_plugin` exits 0.
- `chiliai plugin lint backend/tests/fixtures/sample_plugin_missing_changelog` (new negative-fixture) exits non-zero with the failing check named.
- Lint output is identical-shape to verify output (asserted by test).

### Code touch points
- `backend/plugins/cli.py` (modify — `lint` subcommand)
- `backend/plugins/linter.py` (new — pure-function checks)
- `backend/tests/fixtures/template_plugin/` (new)
- `backend/tests/fixtures/sample_plugin_missing_changelog/` (new — negative fixture)
- `backend/tests/plugins/test_lint.py` (new)
- `docs/plugins/authoring_guide.md` (modify — doc-contract section)

---

## Story _plugins.09: Dogfood — migrate LinearScoringStrategy behind the plugin SPI

**ID:** _plugins.09
**Status:** planned
**Prerequisites:** [_plugins.02, _plugins.04, _plugins.05, _plugins.07, analytics.04]
**Unblocks:** []
**Estimated size:** L

**As a** chiliAI platform team,
**I need** to extract one first-party analytics strategy (`LinearScoringStrategy`) into a plugin loaded through the registry, proving the SPI end-to-end without changing public API behavior,
**so that** v1 SPI is shaken out against a real consumer and there is a worked first-party example for third parties to reference.

### Current State
- `LinearScoringStrategy` lives at `backend/analytics/risk/adapters/linear_strategy.py`; it implements `RiskScoringStrategyProtocol` (`backend/analytics/risk/protocols.py:25`).
- `RiskService` consumes the strategy via constructor injection at `backend/analytics/risk/service.py:38` (`scoring_strategy: RiskScoringStrategyProtocol | None = None`) with a default instantiated inside `__init__`.
- `backend/analytics/risk/service.py:201` re-injects the same default in a factory helper — both sites must keep working when no plugin is enabled.
- `backend/api/dependencies.py` `get_risk_service` (auditor's note) hand-wires the strategy.

### Acceptance Criteria
- [ ] New first-party plugin packaged under `backend/plugins_firstparty/risk_linear/` (packaging decision: in-repo subpackage, installed via the dev extras so `make dev` picks it up; revisit publish-to-PyPI when external plugin distribution is needed).
- [ ] Plugin declares `id="chiliai.risk.linear"`, `capabilities=["AnalyticsStrategyPlugin"]`, `permissions=[]` (pure compute, no IO), exposes `LinearScoringStrategy` via the SPI.
- [ ] `RiskService` refactored to consume a strategy registry: `for strategy in plugin_registry.services_of(RiskScoringStrategyProtocol)` resolves to the plugin when enabled, falls back to the in-tree `LinearScoringStrategy` instance when no plugin is enabled. In-tree class is retained as fallback per spec.
- [ ] `backend/api/dependencies.py` `get_risk_service` no longer hand-constructs `LinearScoringStrategy`; it resolves via `plugin_registry`.
- [ ] Public API behavior unchanged: existing `tests/analytics/risk/` suite passes without modification.
- [ ] New test `backend/tests/plugins/test_dogfood_risk_linear.py` asserts: with the plugin enabled, `RiskService.assess(...)` returns the plugin-supplied strategy result; with the plugin disabled via `POST /plugins/chiliai.risk.linear/disable`, the in-tree fallback engages and `assess(...)` still returns valid output.
- [ ] Lessons-learned section added to `docs/plugins/authoring_guide.md` covering anything painful surfaced during the migration.

### Verification
- `pytest backend/tests/analytics/risk/ backend/tests/plugins/test_dogfood_risk_linear.py -q` green; coverage on `backend/plugins_firstparty/risk_linear/` ≥ 85%.
- `pyright --strict` clean on `backend/analytics/risk/service.py`, `backend/api/dependencies.py`, `backend/plugins_firstparty/risk_linear/`.
- Manual smoke: start API, `POST /analytics/risk/assess` returns expected payload; `POST /plugins/chiliai.risk.linear/disable`; `POST /analytics/risk/assess` still returns valid (fallback) payload; `POST /plugins/chiliai.risk.linear/enable` restores the plugin path.
- Migrating gnn/timeseries/explainability deferred — explicitly tracked as out-of-scope for this story.

### Code touch points
- `backend/plugins_firstparty/risk_linear/__init__.py` (new)
- `backend/plugins_firstparty/risk_linear/plugin.py` (new)
- `backend/plugins_firstparty/risk_linear/chiliai_plugin.toml` (new)
- `backend/plugins_firstparty/risk_linear/README.md` (new)
- `backend/plugins_firstparty/risk_linear/CHANGELOG.md` (new)
- `backend/plugins_firstparty/risk_linear/tests/` (new)
- `backend/analytics/risk/service.py` (modify — registry consumption with fallback)
- `backend/api/dependencies.py` (modify — `get_risk_service` resolves via registry)
- `backend/pyproject.toml` (modify — add `risk-linear-plugin` to dev extras)
- `backend/tests/plugins/test_dogfood_risk_linear.py` (new)
- `docs/plugins/authoring_guide.md` (modify — lessons-learned section)

---

## Story _plugins.10: Per-plugin observability — logs, metrics, traces

**ID:** _plugins.10
**Status:** planned
**Prerequisites:** [_plugins.02, _plugins.04, _observability.03, _observability.05, _observability.07]
**Unblocks:** []
**Estimated size:** L

**As a** platform operator,
**I need** every plugin's logs, metrics, and traces to be automatically tagged with `plugin_id` and `plugin_version`, host-emitted per-call counters and latency histograms, and any uncaught plugin exception logged with manifest provenance without crashing the host,
**so that** plugin behavior is observable, attributable to a specific version, and isolated from host stability.

### Current State
- `structlog` is configured in the host (`backend/pyproject.toml:18` declares the dep) but no plugin-scoped binding exists.
- `prometheus_client` is in deps and `register_metrics(app)` runs at `backend/api/app.py:134` — no `chiliai_plugin_*` namespace is reserved yet.
- The host has no per-plugin tracing-attribute schema.
- `PluginContext` is introduced by _plugins.04 but does not yet carry an observability surface.

### Acceptance Criteria
- [ ] `PluginContext` is extended (modify `backend/plugins/context.py`) with: `logger: structlog.BoundLogger` already bound to `plugin_id` + `plugin_version`; `metrics: PluginMetricsFacade`; `tracer: trace.Tracer` already bound to plugin attributes.
- [ ] Host emits two Prometheus metrics per SPI dispatch: `chiliai_plugin_call_total{plugin_id,capability,result}` (counter) and `chiliai_plugin_call_latency_seconds{plugin_id,capability}` (histogram, default buckets from the observability epic).
- [ ] Metric naming follows `_observability.md` conventions; namespace `chiliai_plugin_*` is documented as reserved and only host code may emit it (plugins use `metrics.emit("custom.name", ...)` which is auto-prefixed `chiliai_plugin_<plugin_id>_custom_name`).
- [ ] Uncaught plugin exceptions caught at the SPI dispatch boundary, logged at `error` with `plugin_id`, `plugin_version`, `capability`, `exc_info=True`; result label on the counter is `error`; host continues; plugin transitions to `FAILED` after N consecutive errors (N configurable in `DomainConfig.plugins[].failure_threshold`, default 5).
- [ ] OpenTelemetry spans for SPI dispatch named `plugin.<capability>` with attributes `plugin.id`, `plugin.version`, `plugin.capability`.
- [ ] Tests in `backend/tests/plugins/test_observability.py` assert metric emission with correct labels, log enrichment, exception swallowing + `FAILED` transition after threshold breaches.
- [ ] Plugin-author docs (`docs/plugins/authoring_guide.md`) gain an Observability section explaining the context surface and the reserved namespace.

### Verification
- `pytest backend/tests/plugins/test_observability.py -q` green; coverage ≥ 85% on `backend/plugins/context.py` and observability helpers.
- `pyright --strict` clean.
- Manual smoke against sample plugin: trigger a permitted call and an erroring call; observe `chiliai_plugin_call_total{plugin_id="sample",result="ok"} 1` and `chiliai_plugin_call_total{plugin_id="sample",result="error"} 1` via `/metrics`.
- Trace export to local OTLP collector (per `_observability.md`) shows `plugin.sample.RiskScoringStrategy` spans.

### Code touch points
- `backend/plugins/context.py` (modify — logger/metrics/tracer wiring)
- `backend/plugins/observability.py` (new — `PluginMetricsFacade`, dispatch wrappers)
- `backend/plugins/registry.py` (modify — wrap SPI dispatch with observability + exception isolation)
- `backend/plugins/lifecycle.py` (modify — FAILED transition on threshold breach)
- `backend/tests/plugins/test_observability.py` (new)
- `docs/plugins/authoring_guide.md` (modify — Observability section)

---

## Story _plugins.11: Surface plugin configuration in DomainConfig

**ID:** _plugins.11
**Status:** planned
**Prerequisites:** [_plugins.02, _plugins.03, config.02, config.05]
**Unblocks:** []
**Estimated size:** M

**As a** platform operator configuring chiliAI for a domain,
**I need** `DomainConfig` to carry per-plugin enablement, version constraints, and typed settings validated against each plugin's `config_schema`,
**so that** plugin behavior is reproducible from configuration and unknown / unsupported plugin versions are rejected at config-load time.

### Current State
- `CapabilitiesConfig` (`backend/config/schema.py:49`) and `AnalyticsConfig` (`backend/config/schema.py:189`) are closed Literal/scalar models with no escape hatch for plugin-supplied settings.
- `config/loader.py` validates the whole `DomainConfig` before any plugin is discovered today — order must change.
- The `*_env_var` secret pattern is documented at `backend/config/schema.py:7-24` and must be reused for plugin settings that carry secrets.
- `config.05` (config UI wizard story) will surface plugin enablement to the frontend — coordinated through this story.

### Acceptance Criteria
- [ ] New `PluginsConfig` Pydantic model added to `backend/config/schema.py`: `plugins: dict[str, PluginConfig]`, where each `PluginConfig` carries `enabled: bool = False`, `version_constraint: str` (PEP 440 range, default `"*"`), `settings: dict[str, Any]` (deferred-validated).
- [ ] `DomainConfig` gains `plugins: PluginsConfig = Field(default_factory=PluginsConfig)`.
- [ ] `config/loader.py` two-phase: phase 1 loads `DomainConfig` with `plugins.settings` un-validated; phase 2 (after `PluginRegistry.discover()`) re-validates each `settings` blob against the plugin's declared `config_schema` (Pydantic model imported via manifest's `config_schema` field).
- [ ] Phase-2 validation failures produce a clear error citing `plugin_id`, the path within `settings`, and the Pydantic validation error.
- [ ] Unknown plugin IDs in config (no manifest discovered) raise `UnknownPluginConfigError` at load time, **unless** the entry has `enabled: false` (in which case it is a warning — operator may stage config ahead of plugin install).
- [ ] Plugin settings carrying secrets MUST use a `*_env_var` field (manifest declares which fields are secret); validation rejects inline secret values in matching fields.
- [ ] Tests in `backend/tests/config/test_plugins_config.py` cover happy path, unknown-plugin error, disabled-unknown warning, version-constraint mismatch, schema-validation failure, inline-secret rejection.

### Verification
- `pytest backend/tests/config/test_plugins_config.py -q` green; coverage on `backend/config/schema.py` and `backend/config/loader.py` ≥ 85% (delta).
- `pyright --strict backend/config/` clean.
- Sample `config/defaults/medicare.yaml` (or current default) extended with an empty `plugins: {}` block — backwards compatible.
- A test domain config enabling the dogfood plugin from _plugins.09 loads cleanly, with phase-2 schema validation observed in logs.

### Code touch points
- `backend/config/schema.py` (modify — `PluginsConfig`, `PluginConfig`, `DomainConfig.plugins` field)
- `backend/config/loader.py` (modify — two-phase plugin-settings validation)
- `backend/config/exceptions.py` (modify or new — `UnknownPluginConfigError`)
- `backend/tests/config/test_plugins_config.py` (new)
- `backend/config/defaults/*.yaml` (modify — add empty `plugins: {}` to each existing default)

---

## Story _plugins.12: Document the v1 backend-only constraint for plugin UI

**ID:** _plugins.12
**Status:** planned
**Prerequisites:** [_plugins.01]
**Unblocks:** []
**Estimated size:** S

**As a** plugin author with frontend ambitions,
**I need** a clear, documented statement that v1 plugin SPI is backend-only, frontend extension points are deferred to v2, and the v2 design options have been enumerated,
**so that** v1 ships without frontend bundling/sandboxing complexity and v2 has a written starting point rather than reopening the brainstorm.

### Current State
- Frontend has no plugin scaffolding: `grep -rn 'plugin' chili_app/src` only matches file-extension strings and the CodeMirror `Extension` type in `chili_app/src/components/YamlEditor.tsx`.
- The auditor's open question on frontend plugin scope is unresolved — v1 commit-or-defer is this story.
- `chili_app/src/api/` has no `/plugins/*` client today.

### Acceptance Criteria
- [ ] SPI spec (`docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md`) gains a `Frontend extension — deferred to v2` section explicitly stating: v1 plugins MAY expose backend APIs under `/plugins/{id}/...` but MUST NOT contribute frontend assets, web components, iframes, or routes.
- [ ] V2 design options documented and parked (not implemented): option A (plugin-supplied dashboard widgets via host-served manifest + iframe/web-component), option B (plugin-declared APIs consumed by host-shipped generic widget components — recommended), option C (full ESM micro-frontend with Module Federation).
- [ ] Recommendation: option B for v2, with rationale (no plugin bundling, no sandboxing complexity, reuses existing host-side generic widget pipeline).
- [ ] `chili_app/README.md` Current State section gains a one-line note: "Plugin UI is deferred to v2; see docs/backlog/_plugins.md story _plugins.12."
- [ ] Tracking note added at the end of the SPI spec: a v2-scoped follow-up story will be created in a future backlog cycle when v2 SPI work is funded.
- [ ] `docs/architecture.md` §14.2 Plugin row gains a sub-bullet "Frontend extension deferred to v2 — see `_plugins.12`."

### Verification
- Manual review of the three doc-edit points; no code changes required.
- Consistency pass (`scripts/backlog_consistency.py`) clean on _plugins.md.
- `grep -n "_plugins.12" docs/architecture.md chili_app/README.md docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` returns at least one hit per file.

### Code touch points
- `docs/superpowers/specs/2026-MM-DD-plugin-spi-v1.md` (modify — `Frontend extension — deferred to v2` section)
- `docs/architecture.md` (modify — §14.2 Plugin row sub-bullet)
- `chili_app/README.md` (modify — Current State note)
