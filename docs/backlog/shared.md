# shared backlog

> **Scope:** Generic platform types (Entity, Relationship, Alert, EvidencePack, KnowledgeBase, TenantId), protocols, error hierarchy, ID conventions, time/clock primitives, validation helpers, structural guardrails.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story shared.01: Promote Alert.severity to the canonical AlertSeverity literal

**ID:** shared.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_multitenancy.01, _plugins.01, graph.01, graph.02, graph.05, graph.06, shared.02]
**Estimated size:** S

**As a** platform contracts owner,
**I need** every consumer of `Alert.severity` to share one typed literal,
**so that** invalid severities are rejected at construction time and `pyright --strict` can statically verify severity handling across monitoring, API, and frontend contracts.

### Current State
- `Alert.severity: str` is typed as a bare string with an inline `TODO(production)` for a `SeverityLevel` enum (`backend/shared/types.py:117-119`).
- The canonical `AlertSeverity = Literal["low","medium","high","critical"]` type already exists in `backend/shared/alerts.py:7-22` alongside `normalize_severity`.
- Monitoring contracts still type severity as `str | None` (`backend/monitoring/models.py:38,99`, `backend/monitoring/service_models.py:53`).
- `AlertSeverity` is not exported from `backend/shared/__init__.py:10-21`, so downstream modules cannot import it from `shared`.

### Acceptance Criteria
- [ ] `Alert.severity` field annotation changed to `AlertSeverity` in `backend/shared/types.py`; inline `TODO(production)` removed.
- [ ] `AlertSeverity` and `normalize_severity` re-exported from `backend/shared/__init__.py` and from `backend/shared/types.py`'s `__all__`.
- [ ] Any value outside `{"low","medium","high","critical"}` constructed into an `Alert` raises a Pydantic `ValidationError` (covered by a test in `backend/tests/shared/test_types.py`).
- [ ] Cross-module callers cited in the audit (`monitoring/models.py`, `monitoring/service_models.py`, alerts router DTOs in `api/`) migrate to `AlertSeverity` or `AlertSeverity | None` as part of `monitoring.*` and `api.*` follow-ups (out of scope here; this story only delivers the shared contract).
- [ ] `pyright --strict` clean for `backend/shared/`.
- [ ] Coverage gate: ≥ 85% on the `shared` package.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green, including a parametrized test that asserts the four valid severities are accepted and at least three invalid strings (`"info"`, `"urgent"`, `""`) raise `ValidationError`.
- `uv run --project backend pyright backend/shared` clean.
- `uv run --project backend ruff check backend/shared` clean.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_types.py` (new | modify)

---

## Story shared.02: Retire the deprecated Alert.acknowledged flag in favor of status

**ID:** shared.02
**Status:** planned
**Prerequisites:** [shared.01]
**Unblocks:** [_plugins.03, embeddings.02, llm.01, llm.10, llm.11]
**Estimated size:** S

**As a** contracts owner,
**I need** the deprecated `Alert.acknowledged: bool` field removed from the shared contract,
**so that** every consumer reads/writes a single `status` literal and we stop carrying a dual-write invariant that diverges silently.

### Current State
- `Alert.acknowledged: bool` lives alongside the canonical `status: Literal[...]` field and is explicitly marked deprecated in `backend/shared/types.py:124-129`.
- No migration story removes it from the contract; consumers in monitoring, API, and the SPA still touch both fields.
- `status` already covers the lifecycle states `"open" | "acknowledged" | "investigating" | "resolved" | "dismissed"`.

### Acceptance Criteria
- [ ] `Alert.acknowledged` field removed from `backend/shared/types.py`.
- [ ] `__all__` and `backend/shared/__init__.py` exports unchanged (no symbol churn beyond field removal).
- [ ] Migration guidance documented in `backend/shared/README.md` (created in shared.17) — single sentence pointing readers to `status == "acknowledged"`.
- [ ] Cross-module migration captured in monitoring, api, and frontend backlog edges (out of scope here; this story only deletes the field from the shared contract once consumers are ready).
- [ ] A pytest in `backend/tests/shared/test_types.py` asserts the field is gone (e.g. `assert "acknowledged" not in Alert.model_fields`).
- [ ] `pyright --strict` clean for `backend/shared/`.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Grep proof: `rg "acknowledged" backend/shared/` returns no matches in `types.py` after the change.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/tests/shared/test_types.py` (modify)

---

## Story shared.03: Enrich EvidencePack with timeline and visual layout fields

**ID:** shared.03
**Status:** planned
**Prerequisites:** [shared.09]
**Unblocks:** [_plugins.07, llm.05]
**Estimated size:** M

**As an** analyst workbench consumer,
**I need** `EvidencePack` to carry structured timeline events and pre-computed visual-layout coordinates,
**so that** the explainability service can hand the SPA a complete evidence bundle without re-deriving timing or layout from raw subgraph IDs.

### Current State
- `EvidencePack` carries only `subgraph_nodes`/`subgraph_edges`/`scores`/`source_documents` with an inline `TODO(production)` for `timeline_events: list[TimelineEntry]` and `visual_layout: dict` (`backend/shared/types.py:134-148`).
- The explainability service today flattens `EvidencePack` into a bag of node/edge ids only (`backend/analytics/explainability/service.py:61-93`).
- There is no `TimelineEntry` contract anywhere in `backend/shared/` (verified by grep).

### Acceptance Criteria
- [ ] New `TimelineEntry` Pydantic model in `backend/shared/types.py` with at least `event_id: str`, `occurred_at: datetime`, `actor_id: str | None`, `subject_id: str | None`, `summary: str`, `payload: dict[str, Any]`.
- [ ] `EvidencePack.timeline_events: list[TimelineEntry]` (default `[]`) and `EvidencePack.visual_layout: dict[str, Any]` (default `{}`) fields added.
- [ ] All `timeline_events[*].occurred_at` defaults derived through the shared clock primitive from shared.09 (not raw `datetime.now`).
- [ ] `EvidencePack.created_at` default is unchanged at `utc_now`; `Alert.created_at` parity with default is captured in shared.14, not here.
- [ ] `TimelineEntry` and the new fields are exported from `backend/shared/__init__.py`.
- [ ] Inline `TODO(production)` on `EvidencePack` removed (`backend/shared/types.py:146-148`).
- [ ] Cross-module follow-ups (analytics.* explainability producer, frontend.* workbench consumer) tracked in their respective backlogs.
- [ ] Pytest coverage exercises round-trip serialization of an `EvidencePack` containing 3 timeline entries and a non-empty `visual_layout`.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared backend/analytics/explainability` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_types.py` (modify)

---

## Story shared.04: Make platform-owned timestamps and version write-controlled

**ID:** shared.04
**Status:** planned
**Prerequisites:** [shared.09]
**Unblocks:** [monitoring.03, shared.16]
**Estimated size:** M

**As a** contracts owner,
**I need** `Entity`/`Relationship` to own `created_at`, `updated_at`, and `version` rather than accept them from adapters or extractors,
**so that** the validator's magic `platform_owned_fields` skip list disappears and no upstream writer can corrupt versioning by passing stale values.

### Current State
- `Entity`/`Relationship` declare `created_at`, `updated_at`, `version` (`backend/shared/types.py:79-103`).
- The validator drops them from property comparison via a magic `platform_owned_fields = {"created_at", "updated_at", "version"}` set (`backend/shared/types.py:193`) instead of refusing them on input or owning the bump on update.
- Nothing prevents adapters/extractors from overwriting `version`/`updated_at` with stale values.

### Acceptance Criteria
- [ ] Introduce a `PlatformOwnedMixin` (or equivalent) in `backend/shared/types.py` that exposes `bump_version()`/`mark_updated(clock)` helpers and rejects external mutation of `version` and `updated_at` via Pydantic validators.
- [ ] `Entity` and `Relationship` either consume the mixin or replicate the same enforcement; constructing either model with explicit non-default `version` from outside the shared package raises a clear `ValidationError` unless a `from_storage=True` escape hatch is set (used by graph adapters loading existing rows).
- [ ] `validate_entity` no longer hand-maintains a `platform_owned_fields` set — the platform-owned fields are now physically separated from `properties` in the model surface.
- [ ] `mark_updated` uses the shared clock from shared.09 (not `datetime.now`).
- [ ] Migration guidance for graph/ingestion/records adapters captured as a cross-module edge in `graph.md`, `ingestion.md`, `records.md`, `database.md`.
- [ ] Pytest covers: round-trip with default platform fields, rejection of stale-version writes, `bump_version()` monotonic increase, `mark_updated()` writes the clock value.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/shared/__init__.py` (modify — export mixin)
- `backend/tests/shared/test_types.py` (modify)

---

## Story shared.05: Centralize and harden entity ID generation conventions

**ID:** shared.05
**Status:** planned
**Prerequisites:** []
**Unblocks:** [embeddings.03, llm.14, rag.14]
**Estimated size:** M

**As a** platform engineer,
**I need** a single `shared.ids` API that produces opaque UUIDs by default and optionally derives stable IDs from `EntityDefinition.natural_key`,
**so that** ingestion can be idempotent on re-runs and downstream KBs can correlate the same logical entity across reloads without bespoke ID logic per call site.

### Current State
- `generate_id` is a UUID4 wrapper (`backend/shared/utils.py:10-12`) and is the only ID strategy across ingestion (`backend/ingestion/extractor.py:93,146,188,256,375,423`, `chunker.py:311,429`, `validator.py:105`), agent (`agent/service.py:47-48`, `workflow_tracking.py:31`), records, monitoring, vectorstore, knowledgebases, and API routers.
- No ULID or k-sortable option exists; no namespace prefix per entity kind.
- `EntityDefinition.natural_key` exists at `backend/shared/types.py:62` but `generate_id()` ignores it; there is no policy for stable IDs that survive re-ingestion.

### Acceptance Criteria
- [ ] New `backend/shared/ids.py` module exposing:
  - `generate_id() -> str` (backwards-compatible UUID4 wrapper; re-export delegates to this).
  - `generate_namespaced_id(entity_type: str) -> str` returning `f"{entity_type}:{uuid4}"`.
  - `derive_stable_id(entity_type: str, natural_key_values: Mapping[str, Any]) -> str` returning a deterministic `uuid5` over `(entity_type, sorted(items))` namespaced under a fixed UUID5 namespace constant.
- [ ] `backend/shared/utils.py:generate_id` becomes a thin re-export pointing to `shared.ids.generate_id` (no behavior change for current callers).
- [ ] `derive_stable_id` rejects empty `natural_key_values` with `ValueError`; uppercase/whitespace normalization documented in docstring.
- [ ] `shared.ids` is the only module in `backend/shared/` allowed to import `uuid`; a unit test asserts the constraint via AST scan.
- [ ] Open question on ID strategy resolved in the design note attached to this story: default stays UUID4; `derive_stable_id` is opt-in for ingestion (no behavior change for live code in this story — only the API surface lands here).
- [ ] Cross-module adoption tracked in `ingestion.md`, `records.md`, `graph.md` (out of scope here).
- [ ] Pytest covers: UUID4 format from `generate_id`, deterministic equality from `derive_stable_id` across two calls with the same input, distinct outputs for distinct entity types with the same natural-key values.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/ids.py` (new)
- `backend/shared/utils.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_ids.py` (new)

---

## Story shared.06: Add a typed cross-module exception hierarchy

**ID:** shared.06
**Status:** planned
**Prerequisites:** []
**Unblocks:** [ingestion.14, shared.08, shared.16]
**Estimated size:** M

**As a** FastAPI exception-handler author,
**I need** every module's root error to inherit from a single `ChiliError` base with canonical `NotFoundError`/`ValidationError`/`ConflictError`/`PermissionError`/`ConfigurationError` subclasses,
**so that** the API gateway can dispatch error → HTTP status with one match table and we stop re-rolling the same error taxonomy in every module.

### Current State
- `shared/exceptions.py:6-7` declares only `ConfigurationError(Exception)`.
- Every module re-rolls its own root error: `agent/exceptions.py:8`, `database/exceptions.py:6`, `embeddings/exceptions.py:6`, `llm/exceptions.py:6`, `monitoring/exceptions.py:6`, `records/exceptions.py:6`, `vectorstore/exceptions.py:6`, `graph/exceptions.py:6`, `rag/exceptions.py:6`.
- API exception mappers cannot match a common base; cross-module `NotFound` / `Conflict` / `Validation` errors are inconsistent.

### Acceptance Criteria
- [ ] `backend/shared/exceptions.py` expanded to declare `ChiliError(Exception)` plus `NotFoundError`, `ValidationError`, `ConflictError`, `PermissionError`, and `ConfigurationError(ChiliError)` (the existing `ConfigurationError` re-parented under `ChiliError`).
- [ ] Each subclass accepts `message: str`, optional `code: str | None`, optional `details: dict[str, Any] | None`; round-trip into a `to_dict()` shape suitable for API serialization.
- [ ] `__all__` updated with all new symbols.
- [ ] Open question resolved: every module's existing root error becomes a subclass of `ChiliError` in module-specific follow-ups (tracked as cross-edges in each module backlog).
- [ ] Pytest covers: subclass relationships, `to_dict()` shape, `repr` includes code/message, raising and catching by `ChiliError` matches all subclasses.

### Verification
- `uv run --project backend pytest backend/tests/shared/test_exceptions.py -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/exceptions.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_exceptions.py` (new)

---

## Story shared.07: Add shared pagination and filter primitives

**ID:** shared.07
**Status:** planned
**Prerequisites:** []
**Unblocks:** [api.08, api.09, ingestion.12]
**Estimated size:** M

**As an** API author,
**I need** one canonical `PageRequest`/`PageResponse`/`CursorPage`/`SortSpec` contract,
**so that** every list endpoint reads `limit`/`offset` (or cursor) consistently, exposes the same `total`/`next_cursor` envelope, and the frontend stops special-casing each endpoint.

### Current State
- Nothing exists yet; every list endpoint re-derives `limit`/`offset`: `api/routers/knowledgebases.py:127-128,269-270`, `api/routers/investigation.py:106-107`, `api/routers/workflows.py:27-28`, `api/routers/analytics.py:47`.
- There is no shared response envelope, no cursor-based option, and no shared `total`/`next_cursor` contract.

### Acceptance Criteria
- [ ] New `backend/shared/pagination.py` module defining:
  - `PageRequest(limit: int = Field(ge=1, le=200, default=50), offset: int = Field(ge=0, default=0))`.
  - `SortSpec(field: str, direction: Literal["asc","desc"] = "asc")` with a `parse(qs: str)` classmethod accepting `"field"` or `"-field"` shorthand.
  - `PageResponse[T](items: list[T], total: int | None, limit: int, offset: int)` as a generic Pydantic model (`Generic[T]`).
  - `CursorPage[T](items: list[T], next_cursor: str | None, previous_cursor: str | None)`.
- [ ] Cursor encoding helper (`encode_cursor`/`decode_cursor`) operates on a dict payload using base64url-of-json; rejects unknown cursors with `ValidationError` from shared.06.
- [ ] Open question resolved in the docstring: offset-paginated is the default contract; cursor-paginated is opt-in for high-cardinality endpoints (analytics, graph traversal).
- [ ] Module exported from `backend/shared/__init__.py`.
- [ ] Pytest covers: limit/offset bounds rejection, `SortSpec.parse` for `"name"`, `"-created_at"`, `""`, cursor round-trip, `PageResponse[Entity]` typed serialization.

### Verification
- `uv run --project backend pytest backend/tests/shared/test_pagination.py -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/pagination.py` (new)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_pagination.py` (new)

---

## Story shared.08: Add a typed Result/Either primitive for fallible boundary operations

**ID:** shared.08
**Status:** planned
**Prerequisites:** [shared.06]
**Unblocks:** []
**Estimated size:** S

**As a** validator/adapter author,
**I need** a small `Result[T, E]` (or `Either`) type with `is_ok`/`is_err`/`unwrap`/`unwrap_err`,
**so that** ingestion validators, records validators, and protocol callers share one return shape for "either a parsed value or a structured error" instead of mixing `list[str]` returns with `raise`.

### Current State
- Nothing exists yet.
- `validate_entity` and `validate_relationship` currently return `list[str]` of error messages (`backend/shared/types.py:173-265`).
- Every adapter raises exceptions instead.
- `records/validation.py:149` and other validators each invent their own return shape.

### Acceptance Criteria
- [ ] New `backend/shared/result.py` defining a `Result[T, E]` dataclass (frozen) with `is_ok: bool`, `value: T | None`, `error: E | None`, plus `ok(value)` / `err(error)` constructors and `unwrap()`/`unwrap_err()` methods.
- [ ] Open question resolved: implemented as a frozen `@dataclass(slots=True)` (zero Pydantic runtime cost on hot paths), with optional `to_pydantic()` helper for API serialization.
- [ ] Generic typing verified by `pyright --strict` (e.g., `Result[Entity, ValidationError]` narrows correctly under `if result.is_ok:`).
- [ ] `unwrap()` on an error result raises the contained error if it is an `Exception`, else raises `ValueError`.
- [ ] Module exported from `backend/shared/__init__.py`.
- [ ] Cross-module adoption is tracked in `ingestion.md`, `records.md`, `config.md` (out of scope here).
- [ ] Pytest covers: `ok`/`err` constructors, `unwrap`/`unwrap_err` happy and error paths, generic narrowing.

### Verification
- `uv run --project backend pytest backend/tests/shared/test_result.py -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/result.py` (new)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_result.py` (new)

---

## Story shared.09: Add Clock protocol and MonotonicTimer wrapper

**ID:** shared.09
**Status:** planned
**Prerequisites:** []
**Unblocks:** [shared.03, shared.04, shared.14]
**Estimated size:** M

**As a** services author,
**I need** a `Clock` protocol and `MonotonicTimer` wrapper that every module consumes instead of `time.perf_counter` / `datetime.now`,
**so that** tests can inject a fake clock deterministically and `utc_now()` is the single source of UTC truth across the backend.

### Current State
- `utc_now()` lives in `shared/utils.py:15-17` but multiple call sites bypass it with raw `datetime.now(timezone.utc)` (`backend/api/state.py:964`, `backend/ingestion/orchestrators/source_documents.py:46`).
- Timing call sites import `time.perf_counter`/`time.monotonic` directly (`backend/monitoring/metrics.py:12,47,54`, `backend/api/middleware/metrics.py:6,60,74`, `backend/api/middleware/auth.py:17,89`).
- Tests fake clocks ad hoc per module because there is no shared injectable clock.

### Acceptance Criteria
- [ ] New `backend/shared/clock.py` module defining:
  - `Clock(Protocol)` with `now() -> datetime` (UTC) and `monotonic() -> float`.
  - `SystemClock` concrete implementation backed by `datetime.now(timezone.utc)` and `time.monotonic()`.
  - `FixedClock(initial: datetime)` test double with `advance(seconds: float)`.
  - `MonotonicTimer(clock: Clock)` context manager exposing `elapsed_seconds` property after exit.
- [ ] `shared.utils.utc_now` becomes `SystemClock().now()` (or equivalent backward-compatible re-export) — existing callers keep working.
- [ ] Open question resolved: `Clock` is a protocol, viral adoption is incremental; tests use `FixedClock` instead of `freezegun` where injection is possible.
- [ ] `Clock`/`SystemClock`/`FixedClock`/`MonotonicTimer` exported from `backend/shared/__init__.py`.
- [ ] Cross-module adoption is tracked in `_observability.md`, `agent.md`, `api.md`, `monitoring.md` (out of scope here).
- [ ] Pytest covers: `SystemClock.now()` returns timezone-aware UTC, `FixedClock.advance()` moves both wall and monotonic forward by the same delta, `MonotonicTimer` records non-negative elapsed.

### Verification
- `uv run --project backend pytest backend/tests/shared/test_clock.py -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/clock.py` (new)
- `backend/shared/utils.py` (modify — `utc_now` delegates)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_clock.py` (new)

---

## Story shared.10: Define the TenantId primitive and tenant_id binding on platform types

**ID:** shared.10
**Status:** planned
**Prerequisites:** []
**Unblocks:** [shared.11]
**Estimated size:** M

**As a** multitenancy architect,
**I need** a `TenantId` type living in `backend/shared/types.py` and a `tenant_id` binding declared on every shared platform model that crosses a tenant boundary,
**so that** every downstream multitenancy story has a single, typed primitive to scope by and the contract is enforced at construction time.

### Current State
- Nothing exists in `backend/shared/` (verified by grep for `TenantId` / `tenant_id` in `backend/shared/`).
- `_multitenancy.md` epic 1 (`_multitenancy.01`) explicitly identifies this as a `shared/types.py` dependency.
- `Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`, `MonitoringObservation` (`backend/shared/types.py:79-371`) all lack a tenant binding.

### Acceptance Criteria
- [ ] New `TenantId = NewType("TenantId", str)` declared in `backend/shared/types.py`; open question resolved in favor of a `NewType` string (UUIDs not required, plain strings keep API ergonomics).
- [ ] New `Tenant` Pydantic model in `backend/shared/types.py` with `id: TenantId`, `display_name: str`, `status: Literal["active","suspended","deleted"]`, `created_at: datetime` (defaulting via shared clock once shared.09 is done; static `utc_now` is acceptable until then to keep this story dependency-free).
- [ ] `Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`, `MonitoringObservation` each gain a `tenant_id: TenantId` field. The field is required for new instances; a temporary `tenant_id: TenantId | None = None` is permitted only if explicitly justified in the docstring with a TODO citing the consumer migration story.
- [ ] `TenantId` and `Tenant` are exported from `backend/shared/types.py.__all__` and `backend/shared/__init__.py`.
- [ ] Pytest covers: `TenantId` is structurally a `str`, `Tenant` round-trips through `model_dump_json`, models constructed without `tenant_id` (when required) raise `ValidationError`, models constructed with two distinct `TenantId`s are not equal.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_types.py` (modify)

---

## Story shared.11: Add KnowledgeBaseId newtype and enrich KnowledgeBase metadata

**ID:** shared.11
**Status:** planned
**Prerequisites:** [shared.10]
**Unblocks:** []
**Estimated size:** S

**As a** dual-graph + KB contracts owner,
**I need** a `KnowledgeBaseId` newtype plus `domain_config_version`, `owner`, and `tags` fields on `KnowledgeBase`,
**so that** the `resolve_kb_scope` return type and every `kb_id: str` boundary stop being raw strings, and audits can pin which domain config was active when a KB was built.

### Current State
- `KnowledgeBase` has an inline `TODO(production)` for `domain_config_version: str | None`, `owner: str | None`, `tags: dict[str, str]` (`backend/shared/types.py:151-165`).
- There is no `KnowledgeBaseId` newtype, so the dual-graph `list[str]` scope returned by `resolve_kb_scope` (`backend/shared/kb_scope.py:29-64`) is untyped at every boundary it crosses.

### Acceptance Criteria
- [ ] `KnowledgeBaseId = NewType("KnowledgeBaseId", str)` declared in `backend/shared/types.py`.
- [ ] `KnowledgeBase.id` annotation switched to `KnowledgeBaseId`.
- [ ] New optional fields on `KnowledgeBase`: `domain_config_version: str | None = None`, `owner: str | None = None`, `tags: dict[str, str] = Field(default_factory=dict)`. Inline `TODO(production)` removed.
- [ ] `KnowledgeBase` tenant binding (from shared.10) is unchanged; `KnowledgeBaseId` is unique per tenant (documented in docstring; uniqueness enforcement is `knowledgebases.*` adapter scope, not shared).
- [ ] `resolve_kb_scope` return type and parameter annotations in `backend/shared/kb_scope.py:29-64` updated to use `list[KnowledgeBaseId]` and `KnowledgeBaseId` respectively; existing tests pass without runtime behavior change.
- [ ] Symbols exported from `backend/shared/__init__.py`.
- [ ] Pytest covers: `KnowledgeBase` construction with and without new optional fields, `resolve_kb_scope` typed return.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/shared/kb_scope.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_kb_scope.py` (modify)

---

## Story shared.12: Add HealthCheckable, Lifecycle, and Measurable cross-cutting protocols

**ID:** shared.12
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** services framework owner,
**I need** `HealthCheckable`, `Lifecycle`, and `Measurable` protocols in `backend/shared/protocols.py`,
**so that** readiness probes, graceful shutdown, and observability exporters have one uniform surface across embeddings, llm, vectorstore, graph, monitoring, and the API gateway.

### Current State
- `shared/protocols.py:61-65` carries a `TODO(production)` to add `HealthCheckable.health_check()`, `Lifecycle.start/stop`, and `Measurable.get_metrics()`.
- Readiness probes can only ping the API itself; individual services have no uniform shutdown or metrics-export surface (`backend/embeddings/adapters/protocols.py:11-22` cites the same gap on `EmbedderProtocol`).

### Acceptance Criteria
- [ ] New protocol declarations in `backend/shared/protocols.py`:
  - `HealthStatus` Pydantic model: `healthy: bool`, `reason: str | None`, `checked_at: datetime`, `details: dict[str, Any] = {}`.
  - `HealthCheckable(Protocol)`: `async def health_check() -> HealthStatus`.
  - `Lifecycle(Protocol)`: `async def start() -> None`, `async def stop() -> None`.
  - `Measurable(Protocol)`: `def get_metrics() -> dict[str, float]`.
- [ ] All four marked `@runtime_checkable`; `__all__` updated.
- [ ] Inline `TODO(production)` at `backend/shared/protocols.py:61-65` removed.
- [ ] `health_check` returns construct uses the shared clock (depends on shared.09 if implemented after; otherwise allowed to use `utc_now` directly with a TODO referencing shared.09).
- [ ] Cross-module adoption tracked in `embeddings.md`, `llm.md`, `vectorstore.md`, `graph.md`, `monitoring.md`, `api.md`, `_observability.md` (out of scope here).
- [ ] Pytest covers: an in-memory dummy class satisfies all three protocols at runtime (`isinstance(obj, HealthCheckable)` etc.), `HealthStatus` round-trips through `model_dump_json`.

### Verification
- `uv run --project backend pytest backend/tests/shared/test_protocols.py -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/protocols.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_protocols.py` (new | modify)

---

## Story shared.13: Document MonitoringObservation placement and export it from shared/__init__

**ID:** shared.13
**Status:** in-progress
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S

**As a** contracts owner,
**I need** `MonitoringObservation` to live in `backend/shared/types.py` so that `records/` can produce it without importing from `monitoring/`,
**so that** the CLAUDE.md Hard Rule 1 cross-module-import gap is closed and both consumers (`monitoring/`, `records/`) depend only on `shared/`.

### Current State
- `MonitoringObservation` was promoted into `backend/shared/types.py:356-371` per commit `0c2c5e2` ("fix(arch): move MonitoringObservation to shared/types.py").
- `monitoring/models.py` re-exports `MonitoringObservation` from `shared/types` so existing internal consumers (`monitoring/service.py`, adapters, `api/state.py`, tests) and external callers via `monitoring/__init__.py` continue to work without import updates.
- The model is **not** exported from `backend/shared/__init__.py:10-21`; new modules wanting to import from the top-level `shared` namespace miss it.

### Acceptance Criteria
- [x] `MonitoringObservation` lives in `backend/shared/types.py` with the same fields and constraints as the original `monitoring/` implementation (`score: float = Field(ge=0.0, le=1.0)`, default `observed_at` via `utc_now`).
- [x] `records/mappers/feed_mapper.py` no longer imports from `monitoring/`.
- [x] `monitoring/models.py` re-exports `MonitoringObservation` from `shared/types` to preserve external API.
- [ ] `MonitoringObservation` added to `backend/shared/__init__.py.__all__` so it can be imported as `from shared import MonitoringObservation` (follow-up captured here so that future readers find the doc).
- [ ] Module docstring at the top of `backend/shared/types.py` updated to explicitly mention `MonitoringObservation` lives here because both `monitoring/` (consumer) and `records/` (producer) need it, and to forbid adding business logic.

### Verification
- `git log --grep="MonitoringObservation"` shows commit `0c2c5e2` and the architecture doc update `6c437e0`.
- `uv run --project backend pytest backend/tests/shared backend/tests/monitoring backend/tests/records -v` green.
- `uv run --project backend pyright backend/shared backend/monitoring backend/records` clean.

### Code touch points
- `backend/shared/types.py` (done)
- `backend/shared/__init__.py` (follow-up: add to `__all__`)
- `backend/monitoring/models.py` (done)
- `backend/records/mappers/feed_mapper.py` (done)

---

## Story shared.14: Add canonical UTC and ISO 8601 (de)serialization helpers

**ID:** shared.14
**Status:** planned
**Prerequisites:** [shared.09]
**Unblocks:** []
**Estimated size:** S

**As an** API + worker author,
**I need** one `json_serialize`/`parse_iso_8601`/`format_iso_8601` helper in `shared.utils`,
**so that** every datetime crossing an API boundary uses a single ISO 8601 contract and Pydantic-default serialization quirks (microseconds, `+00:00` vs `Z`) don't leak inconsistently into responses.

### Current State
- `utils.py:25-29` flags a missing `json_serialize(obj) -> str` with Pydantic + datetime handling.
- API relies on Pydantic's default JSON encoder.
- `EvidencePack.created_at` defaults via `utc_now()` (`backend/shared/types.py:143`) while `Alert.created_at` does not (`backend/shared/types.py:123`).
- `PropertyType.DATE` validation accepts an ISO string but the codebase never standardizes how datetimes are serialized back out.

### Acceptance Criteria
- [ ] `backend/shared/utils.py` (or a new `backend/shared/serialization.py`) gains:
  - `format_iso_8601(value: datetime) -> str` always returns UTC with `Z` suffix and millisecond precision.
  - `parse_iso_8601(value: str) -> datetime` accepts `Z` and `+00:00` and returns timezone-aware UTC; raises `ValueError` on invalid input.
  - `json_serialize(obj: Any) -> str` routes Pydantic `BaseModel` via `model_dump_json` and datetimes via `format_iso_8601`.
- [ ] `Alert.created_at` gains `default_factory=utc_now` so both `Alert` and `EvidencePack` are consistent.
- [ ] `TODO(production)` markers at `backend/shared/utils.py:25-29` related to `json_serialize` removed.
- [ ] Cross-module follow-ups (api response middleware, frontend ISO parsing) tracked in `api.md`, `frontend.md`.
- [ ] Pytest covers: `format_iso_8601` produces `"...Z"`, `parse_iso_8601` round-trip preserves UTC, `json_serialize` handles a nested Pydantic model containing a datetime.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/utils.py` (modify)
- `backend/shared/types.py` (modify — `Alert.created_at` default)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_serialization.py` (new)

---

## Story shared.15: Extract a shared retry/backoff primitive

**ID:** shared.15
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** services author,
**I need** a single `retry(max_attempts, backoff_factor, retryable_exceptions)` decorator and context manager in `backend/shared`,
**so that** embeddings, llm, agent, and events stop hand-rolling their own backoff and we get consistent jitter, exponential-base, and retry-counting semantics across the platform.

### Current State
- `utils.py:25-29` calls out a missing `retry(max_attempts, backoff_factor, retryable_exceptions)` decorator.
- `OpenAIEmbedder._create_embeddings_with_retry` (`backend/embeddings/adapters/openai_adapter.py:115-138`), `OpenAILlmClient`/`AnthropicLlmClient` adapters (`backend/llm/adapters/openai_adapter.py`, `anthropic_adapter.py`), and `agent.run_handler_with_retry` (commit `a0a2a38`) each implement bespoke backoff.

### Acceptance Criteria
- [ ] New `backend/shared/retry.py` module exposing:
  - `RetryPolicy(max_attempts: int = 3, base_delay_seconds: float = 0.1, max_delay_seconds: float = 30.0, backoff_factor: float = 2.0, jitter: bool = True, retryable: tuple[type[Exception], ...] = (Exception,))`.
  - `@retry(policy: RetryPolicy)` decorator working on both sync and async callables.
  - `async with retry_async(policy):` async iterator-style context manager (or equivalent) callers can use to drive retries without a decorator.
  - `RetryExhaustedError(ChiliError)` raised after the final attempt (depends on shared.06 once landed; otherwise a local placeholder with TODO).
- [ ] Retry callback hook: `on_retry: Callable[[int, Exception], None] | None` so callers can emit metrics/logs per attempt.
- [ ] Open question on retry primitive shape resolved: implement as a small dataclass-based policy plus decorator factory; no third-party `tenacity` dependency.
- [ ] Cross-module adoption tracked in `embeddings.md` (epic 3), `llm.md`, `agent.md`, `events.md`.
- [ ] Pytest covers: succeeds on first attempt, succeeds after one retry, raises `RetryExhaustedError` after exhausting attempts, non-retryable exception bypasses retry, jitter randomness bounded, async path works.

### Verification
- `uv run --project backend pytest backend/tests/shared/test_retry.py -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/retry.py` (new)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_retry.py` (new)

---

## Story shared.16: Tighten validation defaults across Entity/Relationship

**ID:** shared.16
**Status:** planned
**Prerequisites:** [shared.04, shared.06]
**Unblocks:** []
**Estimated size:** M

**As a** contracts owner,
**I need** strict pyright on dynamic `dict[str, Any]` properties, registered custom validators, and `extra="forbid"` defaults on shared Pydantic models,
**so that** unannotated keys from adapters and API inputs cannot slip past validation and `Entity.properties` is constrained to JSON-typed values.

### Current State
- `Entity.properties: dict[str, Any]` and `Entity.metadata: dict[str, Any]` (`backend/shared/types.py:84-85`) are deliberately open `Any` maps.
- `validate_entity` is the only enforcement and runs at hand-selected boundaries (ingestion `validator.py:85,94`, records `validation.py:149`).
- API-input paths and adapter-returned objects can today carry arbitrary unannotated keys past `pyright --strict`.

### Acceptance Criteria
- [ ] `JsonValue` type alias added to `backend/shared/types.py`: `JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]`.
- [ ] `Entity.properties` annotation switched to `dict[str, JsonValue]`; `metadata` likewise. Open question resolved: yes, narrow to `JsonValue` and reject non-JSON values at boundaries.
- [ ] `Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase` gain `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected at construction.
- [ ] `validate_entity`/`validate_relationship` return types remain `list[str]` for backwards compatibility in this story; conversion to `Result` (shared.08) is a follow-up cross-edge in `ingestion.md` / `records.md`.
- [ ] A new `register_property_validator(name: str, fn: Callable[[Any], list[str]])` API in `backend/shared/types.py` allows ingestion and records to plug in custom validators referenced by `PropertyDefinition.pattern`-style hooks.
- [ ] Pytest covers: passing a bare `datetime` into `Entity.properties` fails, passing `extra` field into `Alert` fails, registered custom validator runs and returns its errors.

### Verification
- `uv run --project backend pytest backend/tests/shared -v` green.
- `uv run --project backend pyright backend/shared` clean.
- Coverage gate: ≥ 85% on `shared` package.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/shared/__init__.py` (modify)
- `backend/tests/shared/test_types.py` (modify)

---

## Story shared.17: Add shared/README.md and shared/AGENT.md describing module scope

**ID:** shared.17
**Status:** planned
**Prerequisites:** []
**Unblocks:** [shared.18]
**Estimated size:** S

**As a** new contributor (or future Claude/Codex agent),
**I need** a `README.md` and `AGENT.md` at the top of `backend/shared/` describing what belongs in `shared/` and what doesn't,
**so that** refactors stop accidentally importing `config`/`api`/`auth` into `shared` and the architectural policy is visible at the directory level rather than buried in `__init__.py` docstrings.

### Current State
- `backend/shared/` has no `README.md` or `AGENT.md` (verified by `find backend/shared -maxdepth 1 -name "README*" -o -name "AGENT*"` returning nothing).
- The module-level docstrings in `__init__.py:1-5` and `types.py:1-9` carry the policy but it is invisible at the directory level.

### Acceptance Criteria
- [ ] New `backend/shared/README.md` covering:
  - Purpose ("leaf dependency that all other backend modules may import; never imports from any backend module").
  - The "no business logic, no domain types" rule with examples (no `Provider`/`Claim`/`Beneficiary`).
  - Dependency-light invariant (stdlib + Pydantic + structlog + optional OTel only) with the explicit allowed-import list.
  - What lives here (Entity/Relationship/Alert/EvidencePack/KnowledgeBase/MonitoringObservation/TenantId/protocols/exceptions/clock/retry/result/pagination/ids).
  - What does NOT live here (auth/User/Tenant identity at the protocol level — cross-edge to `_multitenancy.md` and `_security.md`).
  - Pointer to `backend/shared/AGENT.md` for agent-specific guardrails.
- [ ] New `backend/shared/AGENT.md` containing the agent-facing operating rules (one-pager): never add backend-module imports here; if you need a new protocol, add it to `protocols.py`; if you need an error class, add it under the `ChiliError` hierarchy in `exceptions.py`; etc.
- [ ] Both files cite `docs/architecture.md` §2.2 / §5.2 as the authority.
- [ ] Both files are listed in the repo's docs-update checklist (the CLAUDE.md rule "update relevant README/AGENT files").
- [ ] No code changes; no new tests required beyond a lightweight `tests/shared/test_repo_docs.py` that asserts both files exist and contain the strings "leaf dependency" and "no domain types".

### Verification
- `uv run --project backend pytest backend/tests/shared/test_repo_docs.py -v` green.
- `cat backend/shared/README.md backend/shared/AGENT.md` shows the policy text.
- `ls backend/shared/{README.md,AGENT.md}` succeeds.

### Code touch points
- `backend/shared/README.md` (new)
- `backend/shared/AGENT.md` (new)
- `backend/tests/shared/test_repo_docs.py` (new)

---

## Story shared.18: Add CI guard forbidding domain types and disallowed imports inside shared/

**ID:** shared.18
**Status:** planned
**Prerequisites:** [shared.17]
**Unblocks:** []
**Estimated size:** M

**As a** platform reviewer,
**I need** a CI check that hard-fails on any file under `backend/shared/` that imports from another backend module, or that defines a class whose name matches a domain identifier (`Provider`, `Claim`, `Beneficiary`, etc.),
**so that** the architectural rule "shared depends on Python stdlib + Pydantic only" stops being policy-only and is enforced at every PR.

### Current State
- The architecture rule "shared depends on Python stdlib only" (`docs/architecture.md` §5.2) is policy-only.
- There is no pyright rule, ruff rule, or import-linter contract preventing `backend/shared/` from importing `config`, `api`, or any module package.
- There is no AST/regex check forbidding domain identifiers like `Provider`/`Claim`/`Beneficiary` from appearing in `shared/`.

### Acceptance Criteria
- [ ] New script `backend/scripts/check_shared_purity.py` (stdlib-only) that walks `backend/shared/` and:
  - Parses each `.py` file with `ast`.
  - Errors on any `import` or `from` statement targeting a backend module other than `shared` itself, `pydantic`, `structlog`, or the optional `opentelemetry` namespace. Allow-list lives in a constant at the top of the script and is documented in `backend/shared/README.md`.
  - Errors on any `ClassDef.name` matching a configurable deny-list (default: `{"Provider","Claim","Beneficiary","ProviderEntity","ClaimEntity","BeneficiaryEntity"}`).
  - Exits non-zero with a per-file summary on the first violation.
- [ ] Open question on mechanism resolved in favor of the hand-rolled AST script (zero extra dependencies, matches existing `scripts/backlog_consistency.py` style).
- [ ] Pytest in `backend/tests/scripts/test_check_shared_purity.py` covers: a clean tree returns 0, an injected disallowed import returns non-zero with file:line, an injected `Provider` class returns non-zero with file:line.
- [ ] CI hook added to the existing GitHub Actions workflow under a `shared-purity` job that runs `uv run --project backend python backend/scripts/check_shared_purity.py` on any PR that touches `backend/shared/`.
- [ ] CI job documented in `backend/shared/README.md` and in `_cicd.md` cross-edge.

### Verification
- `uv run --project backend pytest backend/tests/scripts/test_check_shared_purity.py -v` green.
- `uv run --project backend python backend/scripts/check_shared_purity.py` exits 0 against the current tree.
- A deliberate test commit adding `from api.app import create_app` to `backend/shared/utils.py` fails the new CI job.

### Code touch points
- `backend/scripts/check_shared_purity.py` (new)
- `backend/tests/scripts/test_check_shared_purity.py` (new)
- `.github/workflows/` (modify — add CI job)
- `backend/shared/README.md` (modify — document the guard)
