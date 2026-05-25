## File: docs/backlog/_multitenancy.md

**Scope:** Greenfield introduction of tenant isolation across identity, configuration, persistence, graph/vector/object adapters, KBs, event streams, workflow context, frontend, and quality gates — per `docs/architecture.md` §12.3 and §14.2.

### Epics
1. Define the tenant identity model in `shared/types.py` — Nothing exists yet; no `Tenant`, `TenantId`, or `tenant_id` field exists anywhere in `backend/shared/` (verified by repo-wide grep). Needs greenfield type plus a `tenant_id` field on `User` (`backend/api/middleware/auth.py:52`), `KnowledgeBase`, `Alert`, and `EvidencePack`.
2. Extend `DomainConfig` with a tenant binding and per-tenant overrides — Nothing exists yet; `backend/config/schema.py` has no tenant-related class and `CHILI_CONFIG_PATH` (`backend/config/loader.py:51`) loads a single global config. Architecture §9 calls config per-domain but endgame requires per-tenant config selection/overrides.
3. Resolve tenant context from the JWT claim in API middleware — Nothing exists yet; `User` model at `backend/api/middleware/auth.py:52` only carries `user_id`, `roles`, `email`. No tenant claim is read, validated, or rejected.
4. Add tenant-scoped DI/request context — Nothing exists yet; `backend/api/dependencies.py` has zero tenant references. Need a `get_current_tenant()` dependency, contextvar propagation, and an unauthenticated-tenant default-deny policy.
5. Add `tenant_id` columns + composite indexes to every Postgres table — Nothing exists yet; `backend/database/migrations/versions/0001_persistence_baseline.py` keys all tables (raw_records, observations, entity_metric_history, entity_metrics_current, …) on `knowledge_base_id` only. Need a migration that adds `tenant_id` to every table and to the primary/composite keys + indexes.
6. Enforce tenant scoping in every Postgres query path — Nothing exists yet; depends on Epic 5. Repository/query layer must inject `WHERE tenant_id = :tenant` on every read and write; pyright-level guards against unscoped queries.
7. Isolate graphs per tenant — Nothing exists yet; `backend/graph/adapters/neo4j_adapter.py:143-164` scopes constraints/indexes/transactions on `knowledge_base_id` against a single shared Neo4j database. Decide between per-tenant Neo4j databases vs. strict `(tenant_id, knowledge_base_id)` label/property scoping and implement.
8. Isolate vector collections per tenant — Nothing exists yet; `backend/vectorstore/adapters/qdrant_adapter.py:224` and `in_memory.py:105` namespace solely on `knowledge_base_id`. Need per-tenant collection naming (e.g. `t_{tenant}__kb_{kb}`) in both protocol and adapters.
9. Isolate object-store prefixes per tenant — Nothing exists yet; `backend/storage/adapters/s3_adapter.py:80,199` and `local_fs_adapter.py:31` use a single `base_path` (the only repo reference to "tenants/" is a hard-coded string in `backend/tests/api/test_dependencies.py:257`). Need per-tenant prefix injection at adapter construction or per-write.
10. Scope KnowledgeBase records and operations by tenant — Nothing exists yet; `backend/knowledgebases/models.py` has no `tenant_id`, `backend/shared/kb_scope.py` resolves scope from `DomainConfig` only. Cross-tenant KB resolution is currently possible by ID guessing.
11. Scope Redis Stream names and consumer groups by tenant — Nothing exists yet; `backend/events/adapters/redis_streams.py:46-106` uses caller-provided stream/group names with no tenant prefixing. Need a stream-naming policy (e.g. `t.{tenant}.<stream>`) and consumer-group convention to prevent cross-tenant event leakage.
12. Propagate tenant context through the agent coordinator and workflow envelopes — Nothing exists yet; `backend/agent/coordinator.py` has zero tenant references and event envelopes do not carry tenant. Every workflow step must receive, validate, and forward the originating tenant.
13. Per-tenant configuration loading and switching — Nothing exists yet; `backend/config/loader.py:20` loads a single config from `CHILI_CONFIG_PATH`. Need a per-tenant resolver, cache, and reload policy (likely depends on Epic 2).
14. Frontend tenant context, switcher, and API plumbing — Nothing exists yet; `chili_app/src/` has no tenant references (only `workspace-update` SSE event and CSS class names). Need a current-tenant store, header injection on every API call, switcher UI, and tenant gating in the SPA shell.
15. Cross-tenant query prevention as a hard quality gate — Nothing exists yet; no test in `backend/tests/` exercises tenant isolation. Need adapter-level and end-to-end tests that two tenants cannot read each other's KBs, graphs, vectors, blobs, streams, alerts, or workflows; CI must fail on any leak.
16. Per-tenant capacity, quotas, and rate limits — Nothing exists yet; rate-limiting is itself flagged as deferred in `docs/architecture.md` §12.4. Endgame multi-tenancy needs per-tenant rate limits and storage/compute quotas to prevent noisy-neighbor abuse.

### Provisional cross-file edges
- All epics depend on `_security.md` epic(s) introducing tenant claims in the production IdP profile and JWT validation.
- Epics 1 and 2 must land before nearly every other epic here; they are also `shared.md` and `config.md` prerequisites and likely shared with `_security.md`.
- Epic 5 unblocks Epic 6 and every `database.md` repository story.
- Epic 7 has a cross-edge to `graph.md` (Neo4j multi-database operational story) and to `_infra.md` (per-tenant Neo4j database provisioning).
- Epic 8 has a cross-edge to `vectorstore.md` (Qdrant collection lifecycle) and `_infra.md`.
- Epic 9 has a cross-edge to `storage.md` and `_infra.md` (per-tenant bucket policy if used).
- Epic 10 has a cross-edge to `knowledgebases.md` (KB CRUD + listing API tenant scoping).
- Epic 11 has cross-edges to `events.md` (stream naming policy) and `agent.md` (consumer-group registration).
- Epic 12 has cross-edges to `agent.md` and `monitoring.md` (workflow + alert pipelines must round-trip tenant).
- Epic 13 has cross-edges to `config.md` and to the `_security.md` audit log epic (config changes must record tenant).
- Epic 14 has cross-edges to `frontend.md` (auth context, API client) and to `_security.md` (login flow must surface tenant).
- Epic 15 has cross-edges to every module's test story and to `_observability.md` (tenant label on logs/metrics/traces is part of leak detection).
- Epic 16 has a cross-edge to `_observability.md` (per-tenant metrics) and `_security.md` (abuse protection).

### Open questions
- Tenant granularity: tenant == organization, or also nested workspaces (org → workspace → KB)? Affects shape of `TenantId`, JWT claim, and Epic 1.
- Graph isolation strategy: per-tenant Neo4j database (cleaner, requires Enterprise edition + provisioning automation) vs. strict label/property scoping in the community single-database model? Decision drives Epic 7 scope.
- Vector isolation strategy: per-tenant Qdrant collection vs. shared collection with tenant payload filter? Affects Epic 8 cost/perf tradeoffs.
- Config layering: do tenants override `DomainConfig` wholesale, or only a subset of fields? Affects Epic 2 schema and Epic 13 loader complexity.
- Should `knowledge_base_id` keys be globally unique or `(tenant_id, knowledge_base_id)` composite? Affects every adapter signature touched by Epics 5–11.
- Is data migration of existing single-tenant artifacts in scope, or do we assume a clean cutover where existing data becomes `tenant_id = 'default'`?
- Does the architectural endgame include cross-tenant admin operations (e.g. platform-admin role that can list all tenants)? If so, Epic 4 needs an explicit superuser bypass with audit logging.
