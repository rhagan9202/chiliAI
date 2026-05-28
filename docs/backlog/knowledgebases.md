# knowledgebases backlog

> **Scope:** KB metadata persistence, lifecycle (create/list/get/delete cascade), provenance, document metadata, versioning, audit, RBAC, import/export.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story knowledgebases.01: Add a production-grade Postgres KB metadata adapter

**ID:** knowledgebases.01
**Status:** planned
**Prerequisites:** [database.02]
**Unblocks:** [_multitenancy.10, _security.02, knowledgebases.05, knowledgebases.06, knowledgebases.07, knowledgebases.08, knowledgebases.09, knowledgebases.13, rag.09]
**Estimated size:** L

**As a** platform operator running chiliAI in staging or production,
**I need** a Postgres-backed `KnowledgeBaseRepository` adapter selectable through the existing `CHILI_KB_REPOSITORY_BACKEND` switch,
**so that** KB and document metadata survive process restarts under concurrent API workers without the single-writer JSON-snapshot pattern.

### Current State
- `KnowledgeBaseRepository` protocol declares 12 methods covering KB + document CRUD plus `mark_pending_cleanup` and `get_document_by_content_hash` (`backend/knowledgebases/protocols.py:13-69`).
- Only two adapters ship: `InMemoryKnowledgeBaseRepository` (`backend/knowledgebases/adapters/in_memory.py:13-174`) and `ObjectStoreKnowledgeBaseRepository`, the latter documented as "a single-writer development adapter, not a high-concurrency production metadata database" (`backend/knowledgebases/adapters/object_store.py:15-24`); every mutation rewrites the full JSON snapshot via `_save_snapshot` (`backend/knowledgebases/adapters/object_store.py:200-214`).
- `get_knowledge_base_repository` selects between `in_memory` and `object_store` only (`backend/api/dependencies.py:747-759`) and is `@lru_cache(maxsize=1)`.
- `get_document_by_content_hash` carries an explicit O(n) TODO ("Promote content_hash to an indexed metadata field … before the object-store path moves to production") at `backend/knowledgebases/adapters/object_store.py:191-198`.
- `architecture.md` §14.3 names "Add a production-grade KB metadata adapter/migration path" as the named next-milestone gap for this module.

### Acceptance Criteria
- [ ] `backend/knowledgebases/adapters/postgres.py` implements every method on `KnowledgeBaseRepository` against an injected `ConnectionProvider`.
- [ ] Alembic revision under `backend/database/migrations/versions/` creates `knowledge_bases`, `documents` (with `UNIQUE(knowledge_base_id, content_hash)` and a `content_hash` btree index), and a future-ready `document_versions` table; `ON DELETE CASCADE` from KB to documents is declared.
- [ ] `get_knowledge_base_repository` (`backend/api/dependencies.py:747-759`) accepts `postgres` and constructs `PostgresKnowledgeBaseRepository` via the database module's `ConnectionProvider`; unsupported-backend tuple is updated.
- [ ] Boot-time guardrail refuses to start when `CHILI_ENV in {"staging", "production"}` and the resolved backend is `in_memory` or `object_store`.
- [ ] Contract suite under `backend/tests/knowledgebases/test_repository_contract.py` runs the same scenarios against in-memory, object-store, and Postgres adapters and passes.
- [ ] Coverage ≥ 85 % on `backend/knowledgebases/adapters/postgres.py` (Postgres exercised via the integration-marked profile).
- [ ] `backend/knowledgebases/README.md` documents the new selector value and the migration path from object-store snapshot.
- [ ] `pyright --strict` clean across `backend/knowledgebases/`.

### Verification
- `CHILI_KB_REPOSITORY_BACKEND=postgres uvicorn api.app:create_app --factory --reload --port 8000` starts; `POST /knowledgebases` followed by container restart preserves the KB in subsequent `GET /knowledgebases`.
- `pytest backend/tests/knowledgebases -m "integration or not integration"` green; `pytest --cov=backend/knowledgebases` ≥ 85 %.
- Two concurrent `POST /knowledgebases/{id}/documents` calls with the same `content_hash` produce exactly one persisted document (no duplicate-key crash, idempotent dedup), demonstrated by `pytest backend/tests/knowledgebases/test_postgres_concurrency.py`.
- `CHILI_ENV=production CHILI_KB_REPOSITORY_BACKEND=object_store uvicorn …` fails fast with a clear error citing the guardrail.

### Code touch points
- `backend/knowledgebases/adapters/postgres.py` (new)
- `backend/knowledgebases/adapters/__init__.py` (modify)
- `backend/database/migrations/versions/<rev>_knowledge_bases_plan_c.py` (new)
- `backend/api/dependencies.py` (modify: extend `get_knowledge_base_repository`)
- `backend/tests/knowledgebases/test_repository_contract.py` (new)
- `backend/tests/knowledgebases/test_postgres_concurrency.py` (new)
- `backend/knowledgebases/README.md` (modify)

---

## Story knowledgebases.02: Wire `delete_by_source_document` to the document-delete endpoint

**ID:** knowledgebases.02
**Status:** planned
**Prerequisites:** [knowledgebases.03]
**Unblocks:** [knowledgebases.09, knowledgebases.13, storage.07]
**Estimated size:** M

**As an** analyst who deletes a single document from a KB,
**I need** the API to cascade-remove every entity, relationship, and vector point that document produced,
**so that** investigations and RAG retrieval never surface evidence sourced from a deleted document.

### Current State
- `DELETE /knowledgebases/{kb_id}/documents/{doc_id}` (`backend/api/routers/knowledgebases.py:311-359`) deletes only the object-store payload (`backend/api/routers/knowledgebases.py:355-357`) and the metadata row (`backend/api/routers/knowledgebases.py:359`); it does **not** call `graph_service.delete_by_source_document` or `vector_service.delete_by_source_document`.
- The cascade exists in code only on the re-upload (changed-content) path inside `register_knowledge_base_documents` (`backend/api/routers/knowledgebases.py:430-439`).
- `architecture.md` lines 780 and §14.3 (line 1369) both explicitly call this out: "delete_by_source_document … is not yet wired to the document-delete endpoint" and the named milestone "wire `delete_by_source_document` to the document-delete endpoint".
- KB-delete already establishes the 207 partial-failure pattern (`backend/api/routers/knowledgebases.py:206-241`) that this endpoint can mirror.

### Acceptance Criteria
- [ ] `delete_knowledge_base_document` invokes `graph_service.delete_by_source_document(knowledge_base_id, document_id)` before deleting object-store payloads, and `vector_service.delete_by_source_document(...)` before deleting the metadata row.
- [ ] When any cascade step fails, the endpoint returns 207 with a body shape `{knowledge_base_id, document_id, pending_cleanup, steps[]}` mirroring the KB-delete contract and the metadata row is left intact with the document flagged for retry.
- [ ] On full success the endpoint still returns 204 (existing contract preserved).
- [ ] Test `backend/tests/api/test_knowledgebases_router.py::test_delete_document_cascades_graph_and_vector` asserts both delete calls fired in order and the entity/vector counts dropped to zero.
- [ ] Test for the partial-failure path asserts the 207 body shape and that a follow-up `DELETE` retries the cascade.
- [ ] `frontend.md` consumer note: `DocumentTable` row delete continues to work; 207 surfaces a user-facing retry banner (cross-edge to `api.NN` documentation epic).
- [ ] Coverage ≥ 85 % on the modified router branches.

### Verification
- `make dev` then `curl -X DELETE /knowledgebases/{kb_id}/documents/{doc_id}` after ingesting a fixture PDF; subsequent `GET /investigation/search?q=<extracted_entity>` returns zero hits and Qdrant point count for that KB drops by the expected delta (Neo4j Browser confirms zero `Entity{source_document_id: <doc_id>}`).
- `pytest backend/tests/api/test_knowledgebases_router.py -k delete_document` green.
- Manual fault injection (monkeypatch `graph_service.delete_by_source_document` to raise) returns 207 with `pending_cleanup: true`.

### Code touch points
- `backend/api/routers/knowledgebases.py` (modify `delete_knowledge_base_document` 311-359)
- `backend/tests/api/test_knowledgebases_router.py` (modify / extend)
- `backend/knowledgebases/README.md` (modify: document the 207 contract)
- `docs/architecture.md` (modify: strike the §14.3 milestone bullet)

---

## Story knowledgebases.03: Verify and harden provenance stamping at every KB write site

**ID:** knowledgebases.03
**Status:** planned
**Prerequisites:** []
**Unblocks:** [knowledgebases.02, knowledgebases.10]
**Estimated size:** M

**As a** platform engineer relying on `delete_by_source_document` for cascade correctness,
**I need** every entity, relationship, and vector write site to stamp `shared/provenance.py` keys through a single helper and a contract test that proves it,
**so that** a missing or typo'd provenance key on any new ingestion path cannot silently break cascade deletes, re-ingestion, or audit.

### Current State
- `shared/provenance.py:14-39` defines `SOURCE_KIND_KEY`, `SOURCE_DOCUMENT_ID_KEY`, `SOURCE_CHUNK_ID_KEY`, `SOURCE_RAW_RECORD_ID_KEY`, `SOURCE_FEED_KEY`, `SOURCE_ID_KEY`, and `SOURCE_KIND_DOCUMENT` / `SOURCE_KIND_RECORD`.
- The module docstring states that every write and every read filter must reference these constants — never bare literals — but no enforcement, no shared builder helper, and no end-to-end test prove the contract.
- Write sites live across `backend/ingestion/` (document chunks → entity extraction → graph/vector upsert), `backend/records/` (raw records → entity projection), and `backend/agent/coordinator.py` (graph-build flow); a missing key in any of these breaks `delete_by_source_document`.
- `architecture.md` §7.3 ties cascade correctness, audit, and re-ingestion explicitly to this contract.

### Acceptance Criteria
- [ ] New `shared/provenance.py::build_provenance(kind, *, document_id=None, chunk_id=None, feed=None, raw_record_id=None) -> dict[str, str]` centralizes construction; existing constants are re-exported unchanged.
- [ ] Module-by-module survey in `docs/backlog/_epics_drafts/notes/knowledgebases_provenance_audit.md` (or inline in the PR description) catalogs every entity / relationship / vector / raw-record write site and confirms each calls `build_provenance` (or a wrapper that calls it).
- [ ] Contract test `backend/tests/shared/test_provenance_contract.py` walks every ingestion path (document, raw record, re-upload) end-to-end against in-memory adapters and asserts every persisted entity, relationship, and vector point carries `SOURCE_KIND_KEY`, the kind-appropriate id key (`SOURCE_DOCUMENT_ID_KEY` or `SOURCE_RAW_RECORD_ID_KEY`), and where applicable `SOURCE_CHUNK_ID_KEY`.
- [ ] `pyright --strict` clean on `backend/shared/provenance.py` and updated call sites.
- [ ] Coverage ≥ 85 % on `backend/shared/provenance.py` and the contract-walk test.
- [ ] Cross-edge note added to `docs/backlog/ingestion.md` and `docs/backlog/graph.md` epic descriptions referencing `build_provenance` as the canonical helper.

### Verification
- `pytest backend/tests/shared/test_provenance_contract.py -v` green and exercises ingestion + records paths.
- `grep -rn '"source_document_id"\|"source_kind"\|"source_chunk_id"' backend/ | grep -v 'shared/provenance.py\|tests/'` returns zero non-test bare-literal usages.
- After running an end-to-end ingestion (`scripts/seed_medicare_demo.py` or equivalent), `MATCH (n) WHERE n.source_document_id IS NULL RETURN count(n)` returns 0 in Neo4j and the equivalent payload filter on Qdrant returns 0 points.

### Code touch points
- `backend/shared/provenance.py` (modify: add `build_provenance`)
- `backend/ingestion/extractor.py` (modify call sites)
- `backend/records/projection.py` or equivalent record-write site (modify)
- `backend/agent/coordinator.py` (modify graph-build write sites)
- `backend/tests/shared/test_provenance_contract.py` (new)

---

## Story knowledgebases.04: Strengthen and observe the KB-delete cascade retry path

**ID:** knowledgebases.04
**Status:** planned
**Prerequisites:** [knowledgebases.06]
**Unblocks:** []
**Estimated size:** M

**As an** operator triaging a failed KB-delete cascade,
**I need** the worker retry to consult the per-step persisted status, expose the pending-cleanup state through an admin endpoint, and emit a metric per attempted step,
**so that** a stuck cleanup is visible, retriable on demand, and bounded by a known budget rather than relying on the DLQ wrapper alone.

### Current State
- `handle_knowledge_base_deleted` (`backend/agent/coordinator.py:1702-1731`) retries when `event.cleanup_pending` is true (line 1720) but unconditionally re-issues all 4-5 cascade steps regardless of which originally failed; the 207 body's per-step status is not persisted anywhere the worker can read.
- The KB-delete router writes the 207 body inline (`backend/api/routers/knowledgebases.py:234-241`) and calls `repository.mark_pending_cleanup(knowledge_base_id)` (`backend/api/routers/knowledgebases.py:227`) but discards the `steps[]` array.
- `KbBusyError` blocks every KB mutation while `pending_cleanup=True` (`backend/api/routers/knowledgebases.py:192-196, 331-335, 387-391`) with no operator escape hatch.
- No metrics or structured log line records per-step outcome on retry; `logger.info("retrying KB cleanup", …)` at `backend/agent/coordinator.py:1722` is the only signal.

### Acceptance Criteria
- [ ] `mark_pending_cleanup` accepts an optional `steps: list[CleanupStepStatus]` argument and persists it (Postgres column or `KnowledgeBase.cleanup_steps: list[CleanupStepStatus]`); router writes the 207 body's steps through it.
- [ ] `handle_knowledge_base_deleted` reads the persisted per-step status and only re-runs steps whose last outcome was `failed`; successful steps are skipped.
- [ ] New admin endpoint `GET /knowledgebases/{id}/cleanup-status` returns the persisted pending-cleanup state and per-step outcome (guarded by `require_role("admin")`).
- [ ] New admin endpoint `POST /knowledgebases/{id}/cleanup/retry` re-publishes `KnowledgeBaseDeletedEvent(cleanup_pending=True)` and returns 202 with the current step state.
- [ ] Prometheus counter `chili_kb_cleanup_attempts_total{step,outcome}` incremented on every retry step; histogram `chili_kb_cleanup_duration_seconds{step}` captures latency.
- [ ] Structured log line per retry step with `knowledge_base_id`, `step`, `outcome`, `attempt`, `correlation_id`.
- [ ] Maximum-retry budget surfaced as `CHILI_KB_CLEANUP_MAX_ATTEMPTS` (default 5); exceeding it leaves the KB in a `cleanup_dead_letter` state visible from the admin endpoint.
- [ ] Coverage ≥ 85 % on `backend/agent/coordinator.py::handle_knowledge_base_deleted` and the two new admin routes.

### Verification
- Fault-inject `vector_service.delete_knowledge_base` to raise; trigger `DELETE /knowledgebases/{id}`; observe 207 with `steps[…vector: failed]`; restore the vector service; call `POST /knowledgebases/{id}/cleanup/retry` and confirm only the `vector` step re-runs (graph step is not re-issued) via the metric counter and structured log.
- `curl /metrics | grep chili_kb_cleanup_attempts_total` shows non-zero counts after the retry.
- `pytest backend/tests/agent/test_coordinator.py -k knowledge_base_deleted` and `pytest backend/tests/api/test_knowledgebases_cleanup_admin.py` green.

### Code touch points
- `backend/knowledgebases/models.py` (modify: add `CleanupStepStatus`)
- `backend/knowledgebases/protocols.py` (modify: extend `mark_pending_cleanup` signature)
- `backend/knowledgebases/adapters/in_memory.py`, `object_store.py`, `postgres.py` (modify)
- `backend/api/routers/knowledgebases.py` (modify: persist steps + add 2 admin routes)
- `backend/agent/coordinator.py` (modify `handle_knowledge_base_deleted` 1702-1731)
- `backend/monitoring/metrics.py` or `backend/knowledgebases/metrics.py` (modify: new counter + histogram)
- `backend/tests/agent/test_coordinator.py` (modify)
- `backend/tests/api/test_knowledgebases_cleanup_admin.py` (new)

---

## Story knowledgebases.05: Surface rich KB statistics for the Dashboard

**ID:** knowledgebases.05
**Status:** planned
**Prerequisites:** [knowledgebases.01]
**Unblocks:** [rag.17]
**Estimated size:** M

**As an** analyst landing on the Dashboard,
**I need** each KB card to show `last_ingested_at`, `last_extraction_at`, per-type entity counts, document-status breakdown, and raw-record count,
**so that** I can tell at a glance which KBs are fresh, which are mid-ingest, and which contain the entity types I need without drilling into the Investigation Workbench.

### Current State
- `KnowledgeBase` (`backend/shared/types.py:151-165`) carries `entity_count`, `relationship_count`, `document_count`, `status`, `created_at`, `updated_at`, `pending_cleanup` — and an explicit TODO at lines 164-165 ("Add domain_config_version, owner, tags").
- It does **not** carry `last_ingested_at`, `last_extraction_at`, per-type entity histograms, document-status breakdown, or raw-record count.
- The Dashboard's KB cards and the SSE `knowledge_base_statuses` snapshot reuse projection-time numbers from `project_knowledge_base` (`backend/api/_kb_projection.py:24-44`).
- `_derive_status` (`backend/api/_kb_projection.py:65-80`) already computes `ready` / `building` heuristically; it has no signal for "ingest in progress vs extraction in progress".

### Acceptance Criteria
- [ ] `KnowledgeBase` (or a new `KnowledgeBaseSummary` sibling in `backend/knowledgebases/models.py`) gains `last_ingested_at: datetime | None`, `last_extraction_at: datetime | None`, `entity_type_counts: dict[str, int]`, `document_status_counts: dict[str, int]`, `raw_record_count: int`.
- [ ] `project_knowledge_base` derives the new fields from graph + records services and persists them via `update_summary` (signature extended accordingly).
- [ ] New endpoint `GET /knowledgebases/{id}/statistics` returns the rich shape (guarded by `require_role("viewer")`) so the Dashboard avoids over-fetching when it does not need them inline.
- [ ] Existing `GET /knowledgebases` / `GET /knowledgebases/{id}` continue to return the same JSON shape (new fields opt-in via `?include=statistics` or live only on the new endpoint — pick one and document).
- [ ] OpenAPI schema includes the new fields with descriptions.
- [ ] Dashboard hook (`chili_app/src/hooks/useKnowledgeBaseStatistics.ts`) and KB card component (`chili_app/src/pages/DashboardPage.tsx`) consume the endpoint via TanStack Query.
- [ ] Coverage ≥ 85 % on the projection extension and the new endpoint; Vitest covers the new hook + card branch.

### Verification
- After ingesting two PDFs into a KB, `GET /knowledgebases/{id}/statistics` returns non-empty `entity_type_counts`, `document_status_counts: {"ready": 2}`, and a non-null `last_extraction_at`.
- Dashboard card renders the new figures; Playwright e2e `chili_app/tests/e2e/dashboard-kb-statistics.spec.ts` asserts the card text.
- `pytest backend/tests/api/test_knowledgebases_statistics.py` and `npm --prefix chili_app run test:run -- DashboardPage` green.

### Code touch points
- `backend/shared/types.py` or `backend/knowledgebases/models.py` (modify / new)
- `backend/knowledgebases/protocols.py` (modify `update_summary`)
- `backend/knowledgebases/adapters/{in_memory,object_store,postgres}.py` (modify)
- `backend/api/_kb_projection.py` (modify)
- `backend/api/routers/knowledgebases.py` (new endpoint)
- `chili_app/src/hooks/useKnowledgeBaseStatistics.ts` (new)
- `chili_app/src/pages/DashboardPage.tsx` (modify)
- `chili_app/tests/e2e/dashboard-kb-statistics.spec.ts` (new)
- `backend/tests/api/test_knowledgebases_statistics.py` (new)

---

## Story knowledgebases.06: Add a KB-scoped audit log for create / delete / upload / document-delete

**ID:** knowledgebases.06
**Status:** planned
**Prerequisites:** [knowledgebases.01, _security.06, api.20]
**Unblocks:** [embeddings.09, graph.15, knowledgebases.04, monitoring.12]
**Estimated size:** L

**As a** compliance officer reviewing analyst activity on a KB,
**I need** every KB-router mutation (create, delete, document register, document delete, cleanup retry) to write a typed audit entry with actor, IP, request id, target, and outcome,
**so that** a complete tamper-evident history of who did what to which KB is queryable independently of the pipeline event bus.

### Current State
- No structured audit-event log exists for KB mutations. `routers/knowledgebases.py` publishes `KnowledgeBaseCreatedEvent` (`backend/api/routers/knowledgebases.py:115-117`) and `KnowledgeBaseDeletedEvent` (`backend/api/routers/knowledgebases.py:228-233, 244-249`) on the event bus, but these are pipeline-triggering events: they have no actor identity, no client IP, no request id, no outcome.
- Architecture §14.2 lists "Audit log: Track all analyst actions … for compliance" as medium priority; architecture §7.2 is silent on audit ownership.
- The shared cross-cutting durable audit log lands in `_security.06`; this story carries KB-router-specific entries through that protocol.
- `api.20` (per-request correlation IDs) is the upstream source of `request_id` and `correlation_id` fields the audit entry must carry.

### Acceptance Criteria
- [ ] `KbAuditAction` enum (`create`, `delete`, `document_register`, `document_delete`, `cleanup_retry`) defined in `backend/knowledgebases/audit.py`.
- [ ] Every mutating route in `backend/api/routers/knowledgebases.py` emits an audit entry through the `_security.06` audit-log protocol with `actor_subject`, `actor_roles`, `client_ip`, `request_id`, `correlation_id`, `kb_id`, optional `document_id`, `action`, `outcome` (`succeeded` / `failed` / `partial`), `timestamp`, and a compact `details` dict (e.g., file count, replaced_document_ids).
- [ ] Failed mutations (4xx, 5xx, 207) still emit an audit entry with the appropriate outcome.
- [ ] `GET /knowledgebases/{id}/audit` (admin-only) returns cursor-paginated audit entries scoped to that KB.
- [ ] Audit writes are best-effort with respect to the request: a failure in the audit sink logs an error but does not fail the API response (consistency tradeoff documented in the route docstring).
- [ ] Coverage ≥ 85 % on `backend/knowledgebases/audit.py` and the new endpoint; tests assert audit entries land for every mutation route including the partial-failure path.

### Verification
- `pytest backend/tests/knowledgebases/test_audit.py -v` and `pytest backend/tests/api/test_knowledgebases_audit_endpoint.py` green.
- Curl `DELETE /knowledgebases/{id}` then `GET /knowledgebases/{id}/audit?limit=10` returns the delete entry with the actor's `sub` claim, IP, and `correlation_id` matching the response header.
- Logs include a `kb_audit` structured line per mutation, redacted per `_security.07`.

### Code touch points
- `backend/knowledgebases/audit.py` (new)
- `backend/api/routers/knowledgebases.py` (modify: instrument every mutation route)
- `backend/api/dependencies.py` (modify: inject the audit sink)
- `backend/tests/knowledgebases/test_audit.py` (new)
- `backend/tests/api/test_knowledgebases_audit_endpoint.py` (new)
- `backend/knowledgebases/README.md` (modify)

---

## Story knowledgebases.07: Add per-KB RBAC (KB-level roles, not only global)

**ID:** knowledgebases.07
**Status:** planned
**Prerequisites:** [knowledgebases.01, _security.02]
**Unblocks:** []
**Estimated size:** L

**As a** workspace admin onboarding multiple analyst teams onto the same chiliAI deployment,
**I need** to grant `owner` / `editor` / `viewer` roles on a per-KB basis layered on top of the existing global RBAC,
**so that** a global `analyst` cannot mutate every KB and a global `viewer` cannot read every KB by default.

### Current State
- KB routes currently use global RBAC only: `require_role("analyst")` on create / document-write / document-delete (`backend/api/routers/knowledgebases.py:100, 314, 366`), `require_role("admin")` on KB delete (`backend/api/routers/knowledgebases.py:172`), `require_role("viewer")` on reads (`backend/api/routers/knowledgebases.py:124, 147, 265`).
- `KnowledgeBase` has no `owner` field (the TODO at `backend/shared/types.py:164-165` flags this).
- No KB-membership concept exists in `backend/knowledgebases/` or `backend/api/middleware/rbac.py`; no per-KB ACL.
- Architecture §14.2 names "resource-level authorization" as remaining hardening; `_security.02` carries the cross-cutting resource-authz contract.

### Acceptance Criteria
- [ ] `KbMembership` model (`kb_id`, `subject`, `role: Literal["owner","editor","viewer"]`, `granted_by`, `granted_at`) lives in `backend/knowledgebases/models.py`.
- [ ] `KbMembershipRepository` protocol (`list_for_kb`, `list_for_subject`, `set_role`, `revoke`, `has_role`) with in-memory + Postgres adapters; selectable via env var following the existing pattern.
- [ ] `require_kb_role(role)` dependency in `backend/api/middleware/rbac.py` layers on top of `require_role` and consults `KbMembershipRepository`; global `admin` is always granted; KB-creation auto-grants `owner` to the creator.
- [ ] Every KB route updated to use `require_kb_role` with the appropriate role: read (`viewer`), document write / document delete (`editor`), KB delete (`owner` or global `admin`).
- [ ] Admin endpoints `GET /knowledgebases/{id}/members`, `POST /knowledgebases/{id}/members`, `DELETE /knowledgebases/{id}/members/{subject}` (guarded by KB `owner` or global `admin`).
- [ ] Audit entries (`knowledgebases.06`) cover membership grants/revokes.
- [ ] Coverage ≥ 85 % on `backend/knowledgebases/membership.py` (or the chosen module) and the new endpoints; integration test asserts a non-owner analyst gets 403 on document-write but 200 on read of a KB where they hold `viewer`.

### Verification
- `pytest backend/tests/knowledgebases/test_membership.py` and `pytest backend/tests/api/test_knowledgebases_membership_routes.py` green.
- Manual flow: create user A (global `analyst`), user B (global `analyst`); user A creates KB; user B receives 403 on `POST /knowledgebases/{id}/documents`; user A grants user B `editor`; user B's next POST returns 202.

### Code touch points
- `backend/knowledgebases/models.py` (modify: add `KbMembership`)
- `backend/knowledgebases/membership.py` (new: protocol)
- `backend/knowledgebases/adapters/{in_memory,postgres}.py` (modify / new: membership impls)
- `backend/api/middleware/rbac.py` (modify: add `require_kb_role`)
- `backend/api/routers/knowledgebases.py` (modify: swap deps, add 3 membership routes)
- `backend/api/dependencies.py` (modify: wire membership repo)
- `backend/database/migrations/versions/<rev>_kb_membership.py` (new)
- `backend/tests/knowledgebases/test_membership.py` (new)
- `backend/tests/api/test_knowledgebases_membership_routes.py` (new)

---

## Story knowledgebases.08: Add tenant-scoped KB namespaces

**ID:** knowledgebases.08
**Status:** planned
**Prerequisites:** [knowledgebases.01, _multitenancy.04, _multitenancy.10, database.08]
**Unblocks:** []
**Estimated size:** L

**As a** multi-tenant deployment operator,
**I need** every KB record and every KB repository operation to carry `tenant_id`, and the API to refuse cross-tenant reads or mutations by default,
**so that** tenants cannot enumerate, read, or modify each other's knowledge bases regardless of role.

### Current State
- `KnowledgeBase` has no `tenant_id` field (`backend/shared/types.py:151-165`).
- `KnowledgeBaseRepository` methods take no tenant context (`backend/knowledgebases/protocols.py:13-69`).
- `get_knowledge_base_repository` is `@lru_cache(maxsize=1)` returning a single process-wide repository (`backend/api/dependencies.py:747-759`).
- No tenant filter on `list()`, no tenant column in the (planned-for-knowledgebases.01) Postgres adapter.
- Architecture §14.2 lists multi-tenancy as medium priority; the cross-cutting tenant context lands in `_multitenancy.04` and `_multitenancy.10` defines the KB-level tenant-scoping contract.

### Acceptance Criteria
- [ ] `KnowledgeBase` and `DocumentRecord` carry `tenant_id: str` (non-null).
- [ ] Every `KnowledgeBaseRepository` method takes `tenant_id` as a keyword-only argument (or pulls it from a context); list/get/update/delete reject cross-tenant access.
- [ ] Postgres adapter migration adds `tenant_id NOT NULL` to `knowledge_bases` and `documents`, composite indexes `(tenant_id, id)` / `(tenant_id, content_hash)`, and RLS policies keyed on `SET LOCAL chili.tenant_id` (consistent with `database.08`).
- [ ] KB router resolves the caller's `tenant_id` from the request principal (per `_multitenancy.04`) and passes it through every repository call.
- [ ] `KnowledgeBaseCreatedEvent` / `KnowledgeBaseDeletedEvent` carry `tenant_id`; worker `handle_knowledge_base_deleted` honors it.
- [ ] Cross-tenant access attempt returns 404 (not 403; tenant existence must not leak) and emits an audit entry.
- [ ] Coverage ≥ 85 % on the modified adapters and the router; integration test asserts tenant A cannot see tenant B's KBs in `GET /knowledgebases` or by direct id lookup.

### Verification
- `pytest backend/tests/knowledgebases/test_tenant_scoping.py` and `pytest backend/tests/api/test_knowledgebases_tenant_isolation.py` green.
- Manual: create KB as tenant A; switch JWT to tenant B; `GET /knowledgebases/{id}` returns 404; Postgres `SELECT … FROM knowledge_bases WHERE id = '<A_kb>'` blocked by RLS when `chili.tenant_id` is tenant B.

### Code touch points
- `backend/shared/types.py` (modify: add `tenant_id` to `KnowledgeBase`)
- `backend/knowledgebases/models.py` (modify: `DocumentRecord.tenant_id`)
- `backend/knowledgebases/protocols.py` (modify: every method signature)
- `backend/knowledgebases/adapters/{in_memory,object_store,postgres}.py` (modify)
- `backend/events/types.py` (modify: `KnowledgeBase*Event.tenant_id`)
- `backend/api/routers/knowledgebases.py` (modify: thread tenant context)
- `backend/agent/coordinator.py` (modify `handle_knowledge_base_deleted` 1702-1731)
- `backend/database/migrations/versions/<rev>_knowledge_bases_tenant_id.py` (new)
- `backend/tests/knowledgebases/test_tenant_scoping.py` (new)
- `backend/tests/api/test_knowledgebases_tenant_isolation.py` (new)

---

## Story knowledgebases.09: Add KB versioning / point-in-time snapshots

**ID:** knowledgebases.09
**Status:** planned
**Prerequisites:** [knowledgebases.01, knowledgebases.02, graph.14, vectorstore.04]
**Unblocks:** [knowledgebases.10]
**Estimated size:** L

**As an** analyst reviewing an alert that fired against a KB last week,
**I need** to query the KB graph, vectors, and metadata "as of" a named snapshot,
**so that** the evidence I see matches what the system saw at alert time, even after the KB has accepted new documents or re-ingests since.

### Current State
- A KB's content evolves continuously: documents are added, re-ingested via re-upload idempotency (`backend/api/routers/knowledgebases.py:430-439`), and deleted; entities/relationships are upserted as new documents land.
- Nothing today captures a frozen version of the KB. There is no `KbSnapshot` model, no `POST /knowledgebases/{id}/snapshots`, no `?as_of=<snapshot_id>` query parameter on graph or RAG reads.
- Investigation reproducibility and the dual-graph reference-KB versioning story (architecture §7.4) both depend on this.

### Acceptance Criteria
- [ ] `KbSnapshot` model (`snapshot_id`, `kb_id`, `tenant_id`, `created_at`, `created_by`, `label`, `entity_count`, `relationship_count`, `document_count`, `graph_export_key`, `vector_export_key`, `metadata_export_key`, `checksum`) in `backend/knowledgebases/snapshots.py` (current file is a single 19-line snapshot helper for the object-store adapter; extend or split).
- [ ] `KbSnapshotRepository` protocol with in-memory + Postgres adapters; selectable via env var.
- [ ] `POST /knowledgebases/{id}/snapshots` creates a snapshot by invoking `graph_service.export_snapshot(kb_id)` (cross-edge `graph.14`), `vector_service.export_snapshot(kb_id)` (cross-edge `vectorstore.04`), and persisting the metadata projection; returns 201 with the snapshot record.
- [ ] `GET /knowledgebases/{id}/snapshots` lists snapshots (paginated, tenant- and KB-scoped).
- [ ] `?as_of=<snapshot_id>` query parameter accepted on graph + RAG read paths; reads bypass live state and replay from the snapshot exports.
- [ ] Retention policy via `KbSnapshotRetention` config (max snapshots per KB, max age days); a background prune job runs daily.
- [ ] Snapshot create / delete recorded in the audit log (`knowledgebases.06`).
- [ ] Coverage ≥ 85 % on `backend/knowledgebases/snapshots.py` and the new routes.

### Verification
- `pytest backend/tests/knowledgebases/test_snapshots.py` green; flow: create KB → ingest 1 doc → snapshot S1 → ingest 2nd doc → `GET /investigation/search?q=…&as_of=S1` returns only entities from doc 1.
- Snapshot export round-trips: `POST /knowledgebases/{id}/snapshots` then `GET /knowledgebases/{id}/snapshots/{snapshot_id}/manifest` returns a manifest whose checksum verifies against the stored exports.

### Code touch points
- `backend/knowledgebases/snapshots.py` (modify: add `KbSnapshot`, repository protocol)
- `backend/knowledgebases/adapters/{in_memory,postgres}.py` (modify / new: snapshot impls)
- `backend/api/routers/knowledgebases.py` (modify: snapshot routes)
- `backend/api/routers/investigation.py`, `backend/api/routers/rag.py` (modify: honor `?as_of`)
- `backend/agent/coordinator.py` (modify: snapshot prune handler)
- `backend/tests/knowledgebases/test_snapshots.py` (new)

---

## Story knowledgebases.10: Add KB import / export (domain-pack distribution)

**ID:** knowledgebases.10
**Status:** planned
**Prerequisites:** [knowledgebases.03, knowledgebases.09, graph.14, config.13]
**Unblocks:** []
**Estimated size:** L

**As a** chiliAI distributor shipping a reference Medicare policy KB or a food-supply-chain reference KB,
**I need** to export a portable `KbBundle` artifact (metadata + documents + graph + vectors + provenance) and import it into another deployment atomically,
**so that** reference / domain-pack KBs can be distributed as a single signed artifact rather than rebuilt per deployment.

### Current State
- No code path exports a portable KB bundle. `architecture.md` §14.2 lists "Export / reporting: Generate PDF/CSV reports" as low priority but does not name a KB-bundle export.
- The dual-graph reference-KB story (architecture §7.4) specifically benefits — the reference KB is otherwise rebuilt per deployment.
- Domain-pack distribution at the config layer lands in `config.13`; this story extends it with the KB payload.
- The snapshot primitive (`knowledgebases.09`) and graph snapshot (`graph.14`) provide the export building blocks.

### Acceptance Criteria
- [ ] `KbBundle` schema (zip or tarball of `kb.json`, `documents/`, `graph.jsonl`, `vectors.jsonl`, `provenance.json`, `manifest.json` with `checksum`, `chili_version`, `domain_config_version`, `created_at`, `signature`) defined in `backend/knowledgebases/bundle.py`.
- [ ] `POST /knowledgebases/{id}/export` returns a download URL (signed, time-limited) for the bundle artifact stored under the configured object store.
- [ ] `POST /knowledgebases/import` (multipart upload or signed URL fetch) accepts a bundle, validates the manifest + checksum + (optional) signature, and rebuilds KB metadata, documents, graph, vectors atomically (all-or-nothing); provenance keys (`knowledgebases.03`) round-trip preserved.
- [ ] Import rejects bundles whose `chili_version` is incompatible or whose `domain_config_version` is not loaded; suggests a migration path in the error.
- [ ] Import + export audited via `knowledgebases.06`; export is guarded by KB `owner` (per `knowledgebases.07`), import by global `admin`.
- [ ] Bundle round-trip integration test: export KB A on deployment X, import into deployment Y, assert entity counts, relationship counts, vector counts, and a sample `GET /investigation/search?q=…` answer match.
- [ ] Coverage ≥ 85 % on `backend/knowledgebases/bundle.py` and the new routes.

### Verification
- `pytest backend/tests/knowledgebases/test_bundle_round_trip.py -v` green.
- Manual: `curl -X POST .../export` → download bundle → `curl -X POST .../import -F bundle=@./kb.bundle` on a clean deployment; Neo4j + Qdrant counts match.

### Code touch points
- `backend/knowledgebases/bundle.py` (new)
- `backend/api/routers/knowledgebases.py` (modify: export + import routes)
- `backend/agent/coordinator.py` (modify: long-running import handler — publish `KnowledgeBaseImportRequestedEvent`, handle async)
- `backend/events/types.py` (modify: import events)
- `backend/tests/knowledgebases/test_bundle_round_trip.py` (new)

---

## Story knowledgebases.11: Add cross-KB query primitive (multi-KB investigation)

**ID:** knowledgebases.11
**Status:** planned
**Prerequisites:** [graph.18]
**Unblocks:** []
**Estimated size:** L

**As an** analyst investigating a provider flagged in a claims KB,
**I need** to look up that provider's policy guidance from the reference policy KB in a single query (e.g., match by NPI across both KBs),
**so that** I do not have to manually pivot between KBs to ground an alert against its governing reference data.

### Current State
- Reads can already accept `knowledge_base_ids: list[str]` per the dual-graph contract (architecture §7.4) and `resolve_kb_scope` (`backend/shared/kb_scope.py`) honors `default_reference_kb_id`.
- Cross-KB **property joining** (e.g., matching providers by NPI across a reference policy KB and a claims KB) is explicitly "deferred to consumer layers (RAG context builder, UI presentation)" (architecture §7.4).
- The graph adapter's `query_neighborhood` is single-KB because cross-graph edges are not stored.
- Investigation Workbench has no UI affordance for spanning multiple KBs beyond the resolved primary + default reference (per `2026-05-21-kb-contextual-entry-points-design.md` the picker is single-KB).
- RAG cannot answer "find all providers flagged in any claims KB whose policy guidance comes from this reference KB."

### Acceptance Criteria
- [ ] Architecture decision recorded in `docs/architecture.md` §7.4 between (a) explicit cross-KB join API on the graph service (`graph.find_matching_entities(kb_ids, property_key, property_value)` — preferred), (b) cross-KB vector index keyed on a normalized natural id (NPI, …), (c) virtual edges materialized at projection time.
- [ ] Chosen approach implemented behind feature flag `CHILI_CROSS_KB_QUERY_ENABLED` (default off in production until performance is asserted).
- [ ] New endpoint `POST /investigation/cross-kb-search` accepts `{kb_ids, property_key, property_value, limit}` and returns matched entities per KB.
- [ ] Performance budget asserted: p95 ≤ 250 ms for a 2-KB join on ≤ 10 k entities per KB (measured in a benchmark test under `backend/tests/perf/`).
- [ ] Tenant scoping (`knowledgebases.08`) enforced: cross-KB queries reject KB IDs not owned by the caller's tenant.
- [ ] Coverage ≥ 85 % on the new code paths.

### Verification
- `pytest backend/tests/api/test_cross_kb_search.py` and `pytest backend/tests/perf/test_cross_kb_join_budget.py` green.
- Manual: load Medicare claims KB + reference policy KB, `POST /investigation/cross-kb-search {"property_key":"npi","property_value":"<sample>"}` returns rows from both KBs.

### Code touch points
- `docs/architecture.md` (modify §7.4)
- `backend/graph/protocols.py` (modify: add `find_matching_entities` if approach a)
- `backend/graph/adapters/{in_memory,neo4j}.py` (modify)
- `backend/api/routers/investigation.py` (modify: new route)
- `backend/api/state.py` (modify: cross-KB binding)
- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (modify: optional multi-KB UI hint)
- `backend/tests/api/test_cross_kb_search.py` (new)
- `backend/tests/perf/test_cross_kb_join_budget.py` (new)

---

## Story knowledgebases.12: Add KB metadata observability and consistency self-check

**ID:** knowledgebases.12
**Status:** planned
**Prerequisites:** [_observability.03]
**Unblocks:** []
**Estimated size:** M

**As an** operator suspecting the KB cards on the Dashboard show stale counts,
**I need** metrics that count how often the projection writes a different value than the persisted one, a structured log when projection drift happens, and a periodic self-check job that compares `repository.list_documents` count vs persisted `document_count`,
**so that** projection drift, graph-build event lag, and object-store snapshot bloat are all visible from Prometheus instead of being silent.

### Current State
- The KB metadata projection (`backend/api/_kb_projection.py:24-44`) silently writes derived `status`, `entity_count`, `relationship_count` back through `repository.update_summary` on every read; no metric records how often the persisted values actually changed (a proxy for graph-build event lag).
- No structured log line fires when persisted counts disagree with live graph metrics.
- No periodic self-check job compares `repository.list_documents(...).total` vs the persisted `document_count`.
- No metric on the `ObjectStoreKnowledgeBaseRepository` JSON snapshot size — it grows unbounded with KB count and document count.
- Cross-cutting metrics naming + exporter contract lands in `_observability.03`.

### Acceptance Criteria
- [ ] Prometheus counters `chili_kb_projection_updates_total{field}` (incremented when `update_summary` actually changes a field) and `chili_kb_projection_disagreement_total{field}` (incremented when `_kb_projection.project_knowledge_base` writes a different value than the input).
- [ ] Structured log line `kb_projection_drift` per disagreement with `kb_id`, `field`, `persisted`, `live`, `correlation_id`.
- [ ] New job `KbMetadataSelfCheck` (scheduled via the existing scheduler in `backend/agent/coordinator.py` or a new APScheduler hook) runs hourly and emits gauge `chili_kb_metadata_drift_count{field}` for every disagreement found.
- [ ] Gauge `chili_kb_metadata_snapshot_bytes` (only set when the object-store adapter is active) tracks the JSON blob size.
- [ ] Dashboard panel in `infra/grafana/dashboards/knowledgebases.json` renders the four metrics.
- [ ] Coverage ≥ 85 % on the instrumentation; tests assert each counter fires exactly once per drift event.

### Verification
- `curl /metrics | grep chili_kb_projection` after a synthetic drift (mutate the persisted entity_count directly through the in-memory repo, then call `GET /knowledgebases`) shows the disagreement counter incremented.
- `pytest backend/tests/api/test_kb_projection_observability.py` green.

### Code touch points
- `backend/api/_kb_projection.py` (modify: emit metrics + structured log)
- `backend/knowledgebases/metrics.py` (new or modify)
- `backend/agent/coordinator.py` (modify: schedule self-check)
- `backend/knowledgebases/adapters/object_store.py` (modify: emit snapshot-bytes gauge)
- `infra/grafana/dashboards/knowledgebases.json` (new)
- `backend/tests/api/test_kb_projection_observability.py` (new)

---

## Story knowledgebases.13: Add document re-upload idempotency edge cases and audit

**ID:** knowledgebases.13
**Status:** planned
**Prerequisites:** [knowledgebases.01, knowledgebases.02]
**Unblocks:** []
**Estimated size:** M

**As an** analyst who re-uploads a corrected version of a document,
**I need** the re-upload to be atomic (all-or-nothing across graph, vector, metadata, object store), to record the replacement in a queryable history, and to not split-brain on concurrent uploads of the same content,
**so that** a mid-cascade failure does not leave the KB with deleted metadata and orphaned graph/vector points, and so I can audit what document Y replaced what document X at time T.

### Current State
- The re-upload idempotency path (`backend/api/routers/knowledgebases.py:424-450`) handles the happy path: on a matching `content_hash`, it cascade-deletes graph, vector, metadata row, and object payload of the old document, then re-registers.
- Open edges: (a) if `graph_service.delete_by_source_document` succeeds and `vector_service.delete_by_source_document` fails, the metadata row + object payload are still deleted at lines 434-438, leaving an inconsistent partial state with no `pending_cleanup` flag and no `replaced_document_id` in any audit trail; (b) the `replaced_document_id` is surfaced only on the receipt (line 472) — there is no persisted `document_replacements` history; (c) `repository.get_document_by_content_hash` is O(n) on the object-store snapshot (`backend/knowledgebases/adapters/object_store.py:191-198`); (d) no test covers a concurrent double-upload of the same content racing two API workers on the same `content_hash`.

### Acceptance Criteria
- [ ] Re-upload becomes transactional: graph + vector + metadata + object-store cascade-delete runs through a single try-block; on any step failure, the entire re-upload is rolled back (metadata row + object payload restored) and the API returns 207 with a `steps[]` body mirroring `knowledgebases.02`.
- [ ] New `document_replacements` table / repository (`old_id`, `new_id`, `kb_id`, `tenant_id`, `replaced_at`, `actor`, `content_hash`) backed by the Postgres adapter from `knowledgebases.01`.
- [ ] `replaced_document_id` continues to appear on the receipt **and** is queryable via `GET /knowledgebases/{id}/documents/{doc_id}/history`.
- [ ] Content-hash lookup uses the indexed Postgres column from `knowledgebases.01` (no O(n) scan in production mode).
- [ ] Concurrent-upload test: two workers race the same content; exactly one succeeds with `replaced_document_id`, the other returns 409 (or both succeed transactionally with one replacing the other deterministically); test asserts no orphaned graph or vector points either way.
- [ ] Replacement entries written to the audit log (`knowledgebases.06`) with action `document_register` + `replaced_document_id` detail.
- [ ] Coverage ≥ 85 % on the rewritten path and the new history endpoint.

### Verification
- `pytest backend/tests/api/test_knowledgebases_reupload.py -k "transactional or concurrent or history"` green.
- Fault-inject `vector_service.delete_by_source_document` to raise; re-upload returns 207; subsequent `GET /knowledgebases/{id}/documents/{old_id}` still returns the old record (rollback confirmed).
- `GET /knowledgebases/{id}/documents/{new_id}/history` returns the replacement chain.

### Code touch points
- `backend/api/routers/knowledgebases.py` (modify `register_knowledge_base_documents` 362-475)
- `backend/knowledgebases/models.py` (modify: `DocumentReplacement` model)
- `backend/knowledgebases/protocols.py` (modify: replacement-history methods)
- `backend/knowledgebases/adapters/{in_memory,postgres}.py` (modify)
- `backend/database/migrations/versions/<rev>_document_replacements.py` (new)
- `backend/tests/api/test_knowledgebases_reupload.py` (modify / extend with concurrent + transactional cases)
