# _multitenancy backlog

> **Scope:** Tenant isolation across data, configuration, knowledge bases, graphs, vectors, storage, events, workflows, and frontend context.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story _multitenancy.01: Define the tenant identity model in shared/types.py

**ID:** _multitenancy.01
**Status:** planned
**Prerequisites:** [shared.01]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** a canonical `TenantId` primitive and a `Tenant` domain type living in `shared/types.py`, plus a `tenant_id` field added to every cross-module entity (User, KnowledgeBase, Alert, EvidencePack),
**so that** every downstream module has one authoritative type to scope by tenant instead of inventing local string conventions.

### Current State
- Nothing exists yet. Repo-wide grep for `tenant` returns zero hits in `backend/shared/` and `chili_app/src/`.
- `backend/shared/types.py:165` only has a TODO about adding `owner: str | None` / `tags` for organization — no `Tenant` class.
- `User` model at `backend/api/middleware/auth.py:52` carries `user_id`, `roles`, `email` only; no tenant claim.
- `KnowledgeBase`, `Alert`, `EvidencePack` (in `backend/shared/types.py`) have no `tenant_id` field.
- Only repo reference to "tenants/" is a hard-coded test string at `backend/tests/api/test_dependencies.py:257` (`base_path="tenants/default"`).

### Acceptance Criteria
- [ ] `backend/shared/types.py` exports a `TenantId` NewType (str alias) with validation constraints (non-empty, slug-pattern).
- [ ] `backend/shared/types.py` exports a `Tenant` Pydantic model with at minimum `id: TenantId`, `display_name: str`, `created_at: datetime`, `status: Literal["active","suspended"]`.
- [ ] `User` (`backend/api/middleware/auth.py`) gains a `tenant_id: TenantId` field (non-optional in production profile).
- [ ] `KnowledgeBase`, `Alert`, `EvidencePack` gain a `tenant_id: TenantId` field.
- [ ] pyright --strict clean on `backend/shared/` and `backend/api/middleware/`.
- [ ] Unit tests cover validation of `TenantId` and Pydantic round-trip of `Tenant`.
- [ ] Coverage ≥ 85% on `backend/shared/types.py`.

### Verification
- Run `pyright --strict backend/shared backend/api/middleware`.
- Run `pytest backend/tests/shared/ --cov=backend/shared --cov-fail-under=85`.
- Grep `backend/` for `tenant_id:` and confirm `User`, `KnowledgeBase`, `Alert`, `EvidencePack` all match.

### Code touch points
- `backend/shared/types.py` (modify)
- `backend/api/middleware/auth.py` (modify)
- `backend/tests/shared/test_tenant_types.py` (new)

---

## Story _multitenancy.02: Extend DomainConfig with a tenant binding and per-tenant overrides

**ID:** _multitenancy.02
**Status:** planned
**Prerequisites:** [_multitenancy.01, config.01]
**Unblocks:** []
**Estimated size:** L

**As a** platform operator,
**I need** the `DomainConfig` schema to carry an optional `tenant_id` binding and a structured override layer (tenant overrides on top of platform defaults, scoped to a safe subset of fields),
**so that** the same code can serve multiple tenants with per-tenant icon sets, entity-type display names, and feature gates without a global re-deploy.

### Current State
- Nothing exists yet. `backend/config/schema.py` defines `DomainConfig` (Pydantic) with no tenant-related class.
- `backend/config/loader.py:51` loads a single global config from `CHILI_CONFIG_PATH`.
- Architecture §9 describes config as per-domain; §12.3 / §14.2 require per-tenant binding.

### Acceptance Criteria
- [ ] `backend/config/schema.py` adds `TenantBinding` Pydantic model and an optional `tenant_id: TenantId | None` field on `DomainConfig`.
- [ ] `backend/config/schema.py` adds `TenantOverride` model restricting overridable fields to a documented allow-list (e.g. display strings, icons, alert thresholds — never adapter selection).
- [ ] `DomainConfig.merge_overrides(tenant_id: TenantId)` returns a new `DomainConfig` with tenant overrides applied, raising `InvalidOverrideError` for out-of-allow-list keys.
- [ ] Schema migrations documented in `backend/config/README.md`.
- [ ] Pyright strict clean on `backend/config/`.
- [ ] Coverage ≥ 85% on `backend/config/schema.py`.

### Verification
- `pytest backend/tests/config/test_tenant_overrides.py -v`.
- Confirm a tenant override that mutates `graph.adapter` raises `InvalidOverrideError`.
- Confirm a tenant override that mutates `ui.display_name` succeeds and is reflected in the merged config.

### Code touch points
- `backend/config/schema.py` (modify)
- `backend/config/README.md` (modify)
- `backend/tests/config/test_tenant_overrides.py` (new)

---

## Story _multitenancy.03: Resolve tenant context from the JWT claim in API middleware

**ID:** _multitenancy.03
**Status:** planned
**Prerequisites:** [_multitenancy.01, _security.04, api.01]
**Unblocks:** []
**Estimated size:** M

**As an** authenticated user,
**I need** the API gateway to read my tenant from the validated JWT (`tenant_id` or `org_id` claim) and reject requests where the claim is missing, malformed, or references an unknown tenant,
**so that** every request entering the system has a single trusted tenant identity.

### Current State
- Nothing exists yet. `backend/api/middleware/auth.py:52` `User` carries only `user_id`, `roles`, `email`.
- No tenant claim is read, validated, or rejected.
- `build_anonymous_user()` at `backend/api/middleware/auth.py` produces an unauthenticated principal with no tenant — needs an explicit policy.

### Acceptance Criteria
- [ ] `decode_token` (or its successor) extracts the `tenant_id` claim and populates `User.tenant_id`.
- [ ] Missing tenant claim on an authenticated principal returns 401 with a typed error code (`AUTH_NO_TENANT`).
- [ ] Unknown tenant (not present in tenant registry / config) returns 403 with code `AUTH_UNKNOWN_TENANT`.
- [ ] Anonymous principal path is gated: either fully denied (production profile) or assigned a synthetic `tenant_id="anonymous"` (dev profile) — controlled by an explicit `AuthSettings.anonymous_tenant_policy` setting.
- [ ] Unit tests cover all four paths (valid claim, missing claim, unknown tenant, anonymous-allowed dev path).
- [ ] Coverage ≥ 85% on `backend/api/middleware/auth.py`.

### Verification
- `pytest backend/tests/api/middleware/test_auth_tenant.py -v`.
- Issue a JWT without `tenant_id`, hit `GET /api/healthz` — confirm 401 + `AUTH_NO_TENANT`.
- Issue a JWT with bogus `tenant_id`, confirm 403 + `AUTH_UNKNOWN_TENANT`.

### Code touch points
- `backend/api/middleware/auth.py` (modify)
- `backend/api/middleware/__init__.py` (modify)
- `backend/tests/api/middleware/test_auth_tenant.py` (new)

---

## Story _multitenancy.04: Add tenant-scoped DI and request context

**ID:** _multitenancy.04
**Status:** planned
**Prerequisites:** [_multitenancy.03, api.21]
**Unblocks:** []
**Estimated size:** M

**As a** backend developer,
**I need** a `get_current_tenant()` FastAPI dependency, a `current_tenant_ctx` contextvar propagated to background tasks and event handlers, and a default-deny policy for unauthenticated tenant access,
**so that** every service, repository, and adapter can read the active tenant from a single trusted source instead of threading it through every function signature.

### Current State
- Nothing exists yet. `backend/api/dependencies.py` has zero tenant references.
- `lru_cache`-keyed singletons in `backend/api/dependencies.py` are process-wide — they need to be tenant-aware before any tenant data can be served safely.

### Acceptance Criteria
- [ ] `backend/api/dependencies.py` exports `get_current_tenant()` returning `TenantId`.
- [ ] `backend/shared/context.py` (new) exports a `current_tenant_ctx: ContextVar[TenantId | None]`.
- [ ] A FastAPI middleware sets `current_tenant_ctx` from `User.tenant_id` on every request and clears it on response.
- [ ] Background-task helper (`backend/agent/context.py` or shared util) propagates the contextvar into async tasks and worker handlers.
- [ ] Calling any DI helper that reads tenant context with an unset contextvar raises `MissingTenantContextError` (default deny).
- [ ] Pyright strict clean on touched files; coverage ≥ 85% on contextvar plumbing.

### Verification
- `pytest backend/tests/api/test_tenant_context.py -v`.
- Run a sync handler, await an async background task, confirm contextvar value matches across both.
- Unset contextvar, call a tenant-reading dep, confirm `MissingTenantContextError`.

### Code touch points
- `backend/api/dependencies.py` (modify)
- `backend/api/middleware/__init__.py` (modify)
- `backend/shared/context.py` (new)
- `backend/tests/api/test_tenant_context.py` (new)

---

## Story _multitenancy.05: Add tenant_id columns and composite indexes to every Postgres table

**ID:** _multitenancy.05
**Status:** planned
**Prerequisites:** [_multitenancy.01, database.01, database.08]
**Unblocks:** []
**Estimated size:** L

**As a** platform engineer,
**I need** an Alembic migration that adds `tenant_id text NOT NULL` to every Plan-C table (`raw_records`, `observations`, `entity_metric_history`, `entity_metrics_current`, `risk_score_history`, `alert_history`, plus any tables added before this lands) and rebuilds primary keys and composite indexes to include `tenant_id` as the leading column,
**so that** the physical schema enforces tenant scoping at the database layer rather than relying on application code.

### Current State
- Nothing exists yet. `backend/database/migrations/versions/0001_persistence_baseline.py:31,54,79,98,113,131,144` keys every table on `knowledge_base_id` only.
- No `tenant_id` column or RLS policy exists anywhere.

### Acceptance Criteria
- [ ] New migration `backend/database/migrations/versions/00NN_add_tenant_id.py` adds `tenant_id text NOT NULL` to all tables.
- [ ] Composite primary keys are rebuilt with `tenant_id` as the leading column (e.g. `PRIMARY KEY (tenant_id, knowledge_base_id, record_type, record_id)`).
- [ ] Composite indexes on hot read paths add `tenant_id` as the leading column.
- [ ] Migration provides a backfill strategy: existing rows get `tenant_id = 'default'` (or a configured fallback).
- [ ] `downgrade()` is implemented and tested.
- [ ] Migration is idempotent and re-runnable in a test database.
- [ ] Coverage ≥ 85% on migration tests.

### Verification
- `pytest backend/tests/database/test_migration_tenant_id.py -v`.
- Apply migration to a snapshot database, confirm all tables have `tenant_id` and composite PKs.
- Apply `downgrade`, confirm clean revert.

### Code touch points
- `backend/database/migrations/versions/00NN_add_tenant_id.py` (new)
- `backend/tests/database/test_migration_tenant_id.py` (new)

---

## Story _multitenancy.06: Enforce tenant scoping in every Postgres query path

**ID:** _multitenancy.06
**Status:** planned
**Prerequisites:** [_multitenancy.04, _multitenancy.05, database.02]
**Unblocks:** []
**Estimated size:** L

**As a** backend developer,
**I need** every repository in `backend/database/` to inject `WHERE tenant_id = :tenant` on every read and `INSERT ... tenant_id = :tenant` on every write, with a typed guard that prevents pyright from compiling an unscoped query against a tenant-scoped table,
**so that** application code physically cannot issue a cross-tenant query.

### Current State
- Nothing exists yet. No repository in `backend/database/` reads from `current_tenant_ctx` or accepts a `tenant_id` parameter.
- Depends on Epic 05 for the column to scope on.

### Acceptance Criteria
- [ ] Every public read/write method on every repository in `backend/database/` accepts (or resolves from contextvar) a `tenant_id: TenantId` argument.
- [ ] A `TenantScopedQuery` typed wrapper exists; raw `text()` queries against tenant-scoped tables route through it and are pyright-checked.
- [ ] Attempting to query a tenant-scoped table without a `tenant_id` raises `UnscopedQueryError` at construction time.
- [ ] Optional: PostgreSQL Row-Level Security policy `tenant_isolation` enabled per table, keyed off `SET LOCAL chili.tenant_id` — gated behind a settings flag.
- [ ] Repository tests cover the unscoped-query rejection path.
- [ ] Pyright strict clean on `backend/database/`; coverage ≥ 85%.

### Verification
- `pytest backend/tests/database/ --cov=backend/database --cov-fail-under=85`.
- Construct a repository call without setting contextvar / passing `tenant_id`, confirm `UnscopedQueryError`.
- Run two-tenant integration test (Epic 15) and confirm no cross-tenant rows are returned.

### Code touch points
- `backend/database/repositories/` (modify all)
- `backend/database/exceptions.py` (modify)
- `backend/database/_query.py` (new — `TenantScopedQuery` wrapper)
- `backend/tests/database/test_tenant_scoping.py` (new)

---

## Story _multitenancy.07: Isolate graphs per tenant

**ID:** _multitenancy.07
**Status:** planned
**Prerequisites:** [_multitenancy.04, graph.01]
**Unblocks:** []
**Estimated size:** L

**As a** platform engineer,
**I need** the graph protocol and its in-memory + Neo4j adapters to scope every constraint, index, query, and transaction on `(tenant_id, knowledge_base_id)` — choosing between per-tenant Neo4j databases (Enterprise edition) and strict label/property scoping (Community edition) — with the decision recorded in `docs/architecture.md` §12.3,
**so that** no Cypher query, KB merge, or constraint violation can leak entities or relationships across tenants.

### Current State
- Nothing exists yet. `backend/graph/adapters/neo4j_adapter.py:141-152` defines uniqueness and indexes on `knowledge_base_id` only.
- `Neo4jAdapter.transaction(knowledge_base_id)` at `backend/graph/adapters/neo4j_adapter.py:164` has no tenant scoping.
- All MERGE/MATCH queries (`backend/graph/adapters/neo4j_adapter.py:182,228,231,258,262`) match on `knowledge_base_id` only.

### Acceptance Criteria
- [ ] Decision recorded in `docs/architecture.md` §12.3: per-tenant database OR composite label/property scoping.
- [ ] `GraphRepository` protocol methods take `tenant_id: TenantId` alongside `knowledge_base_id`.
- [ ] `Neo4jAdapter` constraints and indexes include `tenant_id`: `REQUIRE (e.tenant_id, e.knowledge_base_id, e.entity_id) IS UNIQUE`.
- [ ] All MERGE/MATCH/DELETE Cypher includes `tenant_id` predicate; pyright-clean string-template guard.
- [ ] In-memory adapter (`backend/graph/adapters/in_memory.py`) namespaces dicts on `(tenant_id, knowledge_base_id)`.
- [ ] Migration script for existing single-tenant Neo4j data → tagged with `tenant_id='default'`.
- [ ] Coverage ≥ 85% on `backend/graph/adapters/`.

### Verification
- `pytest backend/tests/graph/test_tenant_isolation.py -v` (marked `@pytest.mark.integration` for Neo4j).
- Two-tenant integration test: write entity in tenant A, query tenant B — must return empty result.
- Run Cypher `MATCH (n) WHERE NOT EXISTS(n.tenant_id) RETURN count(n)` on a populated database — must return 0.

### Code touch points
- `backend/graph/protocols.py` (modify)
- `backend/graph/adapters/neo4j_adapter.py` (modify)
- `backend/graph/adapters/in_memory.py` (modify)
- `docs/architecture.md` (modify §12.3)
- `backend/tests/graph/test_tenant_isolation.py` (new)

---

## Story _multitenancy.08: Isolate vector collections per tenant

**ID:** _multitenancy.08
**Status:** planned
**Prerequisites:** [_multitenancy.04, vectorstore.01]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** the vector store protocol and its in-memory + Qdrant adapters to namespace collections on `(tenant_id, knowledge_base_id)` (e.g. collection name `t_{tenant}__kb_{kb}`), with the choice between per-tenant collection vs. shared collection + tenant payload filter recorded in `docs/architecture.md` §12.3,
**so that** vector search results, collection enumeration, and similarity scans cannot return cross-tenant points.

### Current State
- Nothing exists yet. `backend/vectorstore/adapters/qdrant_adapter.py:224` uses `_collection_name(knowledge_base_id)` — no tenant axis.
- `backend/vectorstore/adapters/in_memory.py:105` namespaces purely on `knowledge_base_id`.
- Qdrant adapter methods (`backend/vectorstore/adapters/qdrant_adapter.py:133,158,189`) accept `knowledge_base_id` only.

### Acceptance Criteria
- [ ] Decision recorded in `docs/architecture.md` §12.3: per-tenant collection vs. shared collection + payload filter.
- [ ] `VectorStore` protocol methods take `tenant_id: TenantId` in addition to `knowledge_base_id`.
- [ ] `QdrantVectorStore._collection_name(tenant_id, knowledge_base_id)` returns a tenant-prefixed name; collection enumeration filters by prefix.
- [ ] In-memory adapter keys its namespace dict on `(tenant_id, knowledge_base_id)`.
- [ ] Collection-listing endpoints return only the current tenant's collections.
- [ ] Coverage ≥ 85% on `backend/vectorstore/adapters/`.

### Verification
- `pytest backend/tests/vectorstore/test_tenant_isolation.py -v`.
- Two-tenant integration test (Qdrant): upsert points in tenant A, search tenant B — must return empty result.
- Enumerate collections as tenant A — must not show tenant B's collections.

### Code touch points
- `backend/vectorstore/protocols.py` (modify)
- `backend/vectorstore/adapters/qdrant_adapter.py` (modify)
- `backend/vectorstore/adapters/in_memory.py` (modify)
- `docs/architecture.md` (modify §12.3)
- `backend/tests/vectorstore/test_tenant_isolation.py` (new)

---

## Story _multitenancy.09: Isolate object-store prefixes per tenant

**ID:** _multitenancy.09
**Status:** planned
**Prerequisites:** [_multitenancy.04, storage.01]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** the object-storage protocol and its S3 / local-FS adapters to inject a `tenants/{tenant_id}/` prefix in front of every key on every read, write, list, and delete,
**so that** no raw document, evidence-pack artifact, or projection blob can be addressed across tenants.

### Current State
- Nothing exists yet. `backend/storage/adapters/s3_adapter.py:80,199` uses a single `base_path` parameter with no tenant axis.
- `backend/storage/adapters/local_fs_adapter.py:31` uses a single `base_path`.
- Only "tenants/" reference in the entire repo is a hard-coded test string at `backend/tests/api/test_dependencies.py:257` (`base_path="tenants/default"`).

### Acceptance Criteria
- [ ] `ObjectStorage` protocol methods accept (or resolve via contextvar) a `tenant_id: TenantId`.
- [ ] `S3ObjectStore` and `LocalFileSystemObjectStore` prepend `tenants/{tenant_id}/` to every key.
- [ ] `list_keys(prefix)` is scoped to the current tenant's prefix — cannot escape via `..` or leading `/`.
- [ ] Attempting an unscoped operation raises `UnscopedStorageError`.
- [ ] Tests cover prefix injection on put/get/list/delete and on signed-URL generation.
- [ ] Coverage ≥ 85% on `backend/storage/adapters/`.

### Verification
- `pytest backend/tests/storage/test_tenant_isolation.py -v`.
- Two-tenant test: write a blob as tenant A, attempt to read it via tenant B — must return 404.
- Confirm signed URLs include the tenant prefix and reject path traversal.

### Code touch points
- `backend/storage/protocols.py` (modify)
- `backend/storage/adapters/s3_adapter.py` (modify)
- `backend/storage/adapters/local_fs_adapter.py` (modify)
- `backend/storage/exceptions.py` (modify)
- `backend/tests/storage/test_tenant_isolation.py` (new)

---

## Story _multitenancy.10: Scope KnowledgeBase records and operations by tenant

**ID:** _multitenancy.10
**Status:** planned
**Prerequisites:** [_multitenancy.01, _multitenancy.04, knowledgebases.01]
**Unblocks:** []
**Estimated size:** M

**As an** analyst,
**I need** KnowledgeBase CRUD, listing, scope resolution, and ID lookup to be scoped to my tenant — including `backend/shared/kb_scope.py` resolving from `(tenant_id, DomainConfig)`,
**so that** I cannot enumerate, read, or mutate another tenant's KBs even by guessing IDs.

### Current State
- Nothing exists yet. `backend/knowledgebases/models.py` has no `tenant_id` field.
- `backend/shared/kb_scope.py` resolves scope from `DomainConfig` only — cross-tenant KB resolution is currently possible by ID guessing.
- KB list / get endpoints have no tenant filter.

### Acceptance Criteria
- [ ] `KnowledgeBase` model gains `tenant_id: TenantId` (Epic 01 lands the field; this story enforces it on the KB code paths).
- [ ] `KnowledgeBaseRepository` reads/writes are tenant-scoped via contextvar.
- [ ] `backend/shared/kb_scope.py` takes `(tenant_id, kb_id)` and returns 404 (not 403, to avoid ID enumeration leaks) for cross-tenant lookups.
- [ ] KB list endpoint returns only the current tenant's KBs.
- [ ] KB ID generation includes a tenant prefix or remains UUID — documented decision.
- [ ] Coverage ≥ 85% on `backend/knowledgebases/`.

### Verification
- `pytest backend/tests/knowledgebases/test_tenant_isolation.py -v`.
- Create KB as tenant A, GET as tenant B with the exact KB ID — must return 404.
- List KBs as tenant A — confirm only tenant A's KBs in response.

### Code touch points
- `backend/knowledgebases/models.py` (modify)
- `backend/knowledgebases/service.py` (modify)
- `backend/knowledgebases/repository.py` (modify)
- `backend/shared/kb_scope.py` (modify)
- `backend/tests/knowledgebases/test_tenant_isolation.py` (new)

---

## Story _multitenancy.11: Scope Redis Stream names and consumer groups by tenant

**ID:** _multitenancy.11
**Status:** planned
**Prerequisites:** [_multitenancy.04, events.01, events.11]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** the Redis Streams event bus to scope every stream name and consumer group on the originating tenant (e.g. `t.{tenant}.{event_type}` and consumer group `t.{tenant}.{workflow}`), with the decision (stream-per-tenant vs. shared-stream-with-tenant-envelope) recorded in `docs/architecture.md` §12.3,
**so that** workers, monitoring consumers, and SSE bridges cannot read or replay events from a different tenant.

### Current State
- Nothing exists yet. `backend/events/adapters/redis_streams.py:30-34` uses a caller-provided `stream_name_resolver` with no tenant prefixing.
- `ensure_consumer_group` at `backend/events/adapters/redis_streams.py:46-55` uses a caller-supplied `consumer_group` name verbatim.
- `EventBusSettings.stream_name` is `"{prefix}.{event_type}"` (per events.11 audit) with no tenant segment.

### Acceptance Criteria
- [ ] Decision recorded in `docs/architecture.md` §12.3: stream-per-tenant vs. shared-stream + envelope filter.
- [ ] Event envelope adds a required `tenant_id: TenantId` field.
- [ ] `stream_name_resolver` signature changes to take `(tenant_id, event_type)`.
- [ ] Consumer groups are derived as `t.{tenant}.{workflow}.{consumer_role}`.
- [ ] Publisher refuses to emit an event whose envelope `tenant_id` does not match the contextvar.
- [ ] Reader filters out events whose envelope `tenant_id` does not match the subscribed tenant (defense in depth even if streams are per-tenant).
- [ ] Coverage ≥ 85% on `backend/events/adapters/`.

### Verification
- `pytest backend/tests/events/test_tenant_isolation.py -v`.
- Two-tenant integration test: publish event in tenant A's stream, subscribe as tenant B — must yield nothing.
- Attempt to publish with mismatched envelope tenant — must raise `TenantMismatchError`.

### Code touch points
- `backend/events/protocols.py` (modify)
- `backend/events/adapters/redis_streams.py` (modify)
- `backend/events/runtime.py` (modify)
- `backend/events/types.py` (modify — add `tenant_id` to envelope)
- `docs/architecture.md` (modify §12.3)
- `backend/tests/events/test_tenant_isolation.py` (new)

---

## Story _multitenancy.12: Propagate tenant context through the agent coordinator and workflow envelopes

**ID:** _multitenancy.12
**Status:** planned
**Prerequisites:** [_multitenancy.04, _multitenancy.11, agent.01]
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** the agent coordinator to attach the originating tenant to every workflow run, propagate it through every step handler, and refuse to dispatch a step whose handler receives a tenant different from the run's tenant,
**so that** long-running workflows cannot cross tenants between steps and DLQ replays cannot leak across tenants.

### Current State
- Nothing exists yet. `backend/agent/coordinator.py` has zero tenant references.
- Workflow envelopes / run records carry no tenant.
- Worker handlers do not set or read `current_tenant_ctx`.

### Acceptance Criteria
- [ ] Workflow run records include `tenant_id: TenantId`.
- [ ] Coordinator sets `current_tenant_ctx` before invoking each step handler, clears it after.
- [ ] Step handlers that read `current_tenant_ctx` see the run's tenant — verified by unit test with a forked async task.
- [ ] DLQ replay re-establishes the original tenant context.
- [ ] A step handler that mutates a different tenant's data (via shared services) raises `TenantMismatchError` and is recorded.
- [ ] Coverage ≥ 85% on `backend/agent/`.

### Verification
- `pytest backend/tests/agent/test_tenant_context.py -v`.
- Run a 3-step workflow as tenant A, inspect logs/traces — every step carries `tenant_id=A`.
- Replay a DLQ event from tenant A, confirm context is restored.

### Code touch points
- `backend/agent/coordinator.py` (modify)
- `backend/agent/context.py` (new or modify)
- `backend/agent/models.py` (modify — run record schema)
- `backend/tests/agent/test_tenant_context.py` (new)

---

## Story _multitenancy.13: Per-tenant configuration loading and switching

**ID:** _multitenancy.13
**Status:** planned
**Prerequisites:** [_multitenancy.02, _multitenancy.04, config.11]
**Unblocks:** []
**Estimated size:** L

**As a** platform operator,
**I need** the config loader to resolve a `DomainConfig` from `(tenant_id, base config)` — merging tenant overrides per Epic 02 — with per-tenant cache eviction on update and a reload policy that does not require restarting the worker,
**so that** changing a tenant's icon set or alert thresholds takes effect without redeploying or affecting other tenants.

### Current State
- Nothing exists yet. `backend/config/loader.py:20` loads a single global config from `CHILI_CONFIG_PATH`.
- No per-tenant cache; no reload trigger.

### Acceptance Criteria
- [ ] `backend/config/loader.py` exposes `load_for_tenant(tenant_id: TenantId) -> DomainConfig`.
- [ ] Per-tenant cache (e.g. `dict[TenantId, DomainConfig]`) with explicit `invalidate(tenant_id)` API.
- [ ] DI helpers in `backend/api/dependencies.py` keyed on `tenant_id` (no global `lru_cache` shadowing tenant state).
- [ ] An admin endpoint or event triggers `invalidate(tenant_id)` and confirms eviction.
- [ ] Audit log entry written on config reload (cross-edge to `_security.md` audit log).
- [ ] Coverage ≥ 85% on `backend/config/`.

### Verification
- `pytest backend/tests/config/test_per_tenant_loader.py -v`.
- Load config for tenant A, mutate file/source, invalidate, reload — confirm new value served.
- Confirm tenant B's cache is untouched when tenant A is invalidated.

### Code touch points
- `backend/config/loader.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/api/routers/config.py` (modify — add invalidate endpoint)
- `backend/tests/config/test_per_tenant_loader.py` (new)

---

## Story _multitenancy.14: Frontend tenant context, switcher, and API plumbing

**ID:** _multitenancy.14
**Status:** planned
**Prerequisites:** [_multitenancy.03, _multitenancy.10, frontend.01, frontend.19]
**Unblocks:** []
**Estimated size:** L

**As an** analyst working in a multi-tenant deployment,
**I need** the SPA to maintain a current-tenant store, inject the tenant on every API call (header or path, matching backend resolution), render a TopBar tenant switcher for users with multi-tenant membership, and gate the app shell behind tenant resolution,
**so that** I cannot accidentally issue a query against the wrong tenant.

### Current State
- Nothing exists yet. `chili_app/src/` has zero non-test tenant references (grep returns only `workspace-update` SSE event and CSS class names).
- No tenant store, switcher, or header injection.

### Acceptance Criteria
- [ ] Zustand `useTenantStore` exposes `currentTenantId`, `availableTenants`, `setTenant`.
- [ ] API client (`chili_app/src/api/`) injects the current tenant on every request via `X-Chili-Tenant` header (or path prefix — match backend Epic 03 decision).
- [ ] TopBar renders a tenant switcher for users with more than one tenant in their JWT claim; switching invalidates TanStack Query caches.
- [ ] App shell renders a tenant-required gate before any KB / workbench routes mount.
- [ ] SSE / WebSocket connections include tenant identity at handshake.
- [ ] Unit tests (vitest) cover store, API injection, and switcher.
- [ ] Playwright e2e: log in as multi-tenant user, switch tenants, confirm KB list changes.

### Verification
- `npm run test:run` and `npm run test:e2e` in `chili_app/`.
- Open browser DevTools network tab — confirm every request carries the tenant header.

### Code touch points
- `chili_app/src/stores/tenantStore.ts` (new)
- `chili_app/src/api/client.ts` (modify)
- `chili_app/src/components/TopBar/TenantSwitcher.tsx` (new)
- `chili_app/src/AppShell.tsx` (modify)
- `chili_app/tests/stores/tenantStore.test.ts` (new)
- `chili_app/e2e/tenant-switching.spec.ts` (new)

---

## Story _multitenancy.15: Cross-tenant query prevention as a hard quality gate

**ID:** _multitenancy.15
**Status:** planned
**Prerequisites:** [_multitenancy.06, _multitenancy.07, _multitenancy.08, _multitenancy.09, _multitenancy.10, _multitenancy.11, _multitenancy.12]
**Unblocks:** []
**Estimated size:** L

**As a** security reviewer,
**I need** a dedicated test suite that, for two distinct tenants A and B, asserts that B cannot read A's KBs, graph entities, vector points, blobs, streams, alerts, or workflow runs through any code path — and CI fails the build on any leak,
**so that** every future change is automatically gated on multi-tenant isolation.

### Current State
- Nothing exists yet. No test in `backend/tests/` exercises tenant isolation.
- Each per-adapter epic ships its own isolation test, but no cross-cutting suite verifies them holistically.

### Acceptance Criteria
- [ ] New test module `backend/tests/multitenancy/test_isolation_matrix.py` parametrises over (resource_type × operation) pairs covering: KB CRUD, graph read/write, vector search, storage put/get, event publish/subscribe, alert read, workflow status read.
- [ ] Each parametrised case seeds tenant A, switches to tenant B, attempts the operation, asserts 404 / empty / `MissingTenantContextError`.
- [ ] CI job `pytest backend/tests/multitenancy/` runs on every PR and gates merge.
- [ ] Coverage ≥ 85% on the test module itself (sanity check that all branches are exercised).
- [ ] Frontend e2e covers cross-tenant URL probing: navigating to tenant A's KB URL while logged in as tenant B returns the access-denied page.

### Verification
- `pytest backend/tests/multitenancy/ -v`.
- `npm run test:e2e -- --grep cross-tenant` in `chili_app/`.
- Intentionally remove tenant filter from one repository, confirm test suite goes red.

### Code touch points
- `backend/tests/multitenancy/test_isolation_matrix.py` (new)
- `backend/tests/multitenancy/conftest.py` (new — two-tenant fixtures)
- `chili_app/e2e/cross-tenant-isolation.spec.ts` (new)
- `.github/workflows/ci.yaml` (modify — gate merge on suite)

---

## Story _multitenancy.16: Per-tenant capacity, quotas, and rate limits

**ID:** _multitenancy.16
**Status:** planned
**Prerequisites:** [_multitenancy.04, api.18]
**Unblocks:** []
**Estimated size:** L

**As a** platform operator,
**I need** per-tenant rate limits (requests/min on the API gateway, RAG concurrency cap), storage quotas (object-store bytes, vector-point count), and compute quotas (workflow concurrency, LLM token budget) — with metrics exposed for monitoring and a 429/403 response shape when a tenant exceeds its budget,
**so that** a single noisy tenant cannot degrade service or drive costs for the rest of the platform.

### Current State
- Nothing exists yet. `docs/architecture.md` §12.4 explicitly defers rate limiting.
- No per-tenant quota counter, storage tally, or LLM token budget exists anywhere.

### Acceptance Criteria
- [ ] `TenantQuotaConfig` Pydantic model (request rate, storage bytes, vector points, workflow concurrency, monthly LLM tokens) lives in `backend/config/schema.py` as part of the tenant binding.
- [ ] Redis token-bucket per `(tenant_id, dimension)` enforces request rate at the API gateway and RAG service entry points.
- [ ] Storage adapters reject writes that would exceed tenant's byte quota with `StorageQuotaExceededError`.
- [ ] LLM call path checks monthly token budget pre-call, refuses with `LlmBudgetExceededError` if exceeded.
- [ ] 429 / 403 responses include `Retry-After` and a JSON body with quota name + current usage + limit.
- [ ] Prometheus metrics: `chili_tenant_quota_usage{tenant,dimension}` / `chili_tenant_quota_limit{tenant,dimension}`.
- [ ] Coverage ≥ 85% on quota-enforcement code paths.

### Verification
- `pytest backend/tests/multitenancy/test_quotas.py -v`.
- Load-test tenant A above its rate limit, confirm 429 + correct `Retry-After`.
- Drive tenant A above storage quota, confirm upload rejected; confirm tenant B is unaffected.

### Code touch points
- `backend/config/schema.py` (modify — add `TenantQuotaConfig`)
- `backend/api/middleware/rate_limit.py` (new or modify)
- `backend/storage/adapters/_quota.py` (new)
- `backend/llm/_budget.py` (new)
- `backend/rag/service.py` (modify — quota check on entry)
- `backend/tests/multitenancy/test_quotas.py` (new)
