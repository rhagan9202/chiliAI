## File: docs/backlog/knowledgebases.md

**Scope:** KB and document metadata persistence (`knowledgebases/` module), its repository protocol + adapters, the KB API router cascades (create/list/get/delete/document register/delete), provenance integration, the live KB projection contract, and the production-grade gaps explicitly called out in `architecture.md` §7 and §14.3.

Source-of-truth audit of `backend/knowledgebases/` and `backend/api/routers/knowledgebases.py` against `docs/architecture.md` §7 (entire section: 7.1 operations, 7.2 metadata projection, 7.3 provenance, 7.4 dual-graph), §5.2 knowledgebases row, §14.3 next-milestone gaps, and the live spec `2026-05-21-kb-contextual-entry-points-design.md`. The module is recent (introduced for KB + document metadata persistence; replaces `api/_kb_store.py`).

Done and intentionally **not** carried forward as epics (verified in code):
- `KnowledgeBaseRepository` protocol + `InMemoryKnowledgeBaseRepository` + `ObjectStoreKnowledgeBaseRepository` (`knowledgebases/protocols.py:14`, `adapters/in_memory.py:13`, `adapters/object_store.py:15`).
- KB lifecycle CRUD: `POST /knowledgebases`, `GET /knowledgebases`, `GET /knowledgebases/{id}`, `DELETE /knowledgebases/{id}` (`api/routers/knowledgebases.py:96-250`).
- 5-step KB-delete cascade (graph → vector → raw_records → object_store → metadata) with 207 partial-failure body, `pending_cleanup` flag, and worker retry via `handle_knowledge_base_deleted` (`api/routers/knowledgebases.py:206-250`, `agent/coordinator.py:1702-1731`).
- Workflow-busy 409 guard via `WorkflowBusyTracker` on KB delete + document register + document delete (`api/routers/knowledgebases.py:199, 337, 393`).
- Re-upload idempotency via SHA-256 `content_hash` → `replaced_document_id` returned on the receipt; existing doc's graph/vector/metadata/object payload are cascade-deleted before re-registering (`api/routers/knowledgebases.py:424-450`, `models.py:24`, `repository.get_document_by_content_hash`).
- KB live metadata projection (`project_knowledge_base` merges live graph metrics + object-store signals; persists back through `update_summary`; used by list/detail/SSE workspace snapshots) (`api/_kb_projection.py:24-44`).
- Dual-graph read scope for KB reads via `shared/kb_scope.py:29 resolve_kb_scope` honoring `default_reference_kb_id` (per architecture §7.4).
- Provenance constants module (`shared/provenance.py:14-39`) defining `SOURCE_KIND_KEY`, `SOURCE_DOCUMENT_ID_KEY`, `SOURCE_CHUNK_ID_KEY`, etc., consumed by graph + vector delete-by-source-document paths.
- `KnowledgeBaseCreatedEvent` / `KnowledgeBaseDeletedEvent` publish on create/delete (`api/routers/knowledgebases.py:115, 228, 244`).

---

## Epic 1: Add a production-grade Postgres KB metadata adapter

**Gap:** `knowledgebases/adapters/` ships only `InMemoryKnowledgeBaseRepository` and `ObjectStoreKnowledgeBaseRepository`. The latter is explicitly "a single-writer development adapter, not a high-concurrency production metadata database" (`adapters/object_store.py:16-24`); every mutation rewrites a single JSON blob. `architecture.md:1369` explicitly flags "Add a production-grade KB metadata adapter/migration path" as the next-milestone gap for this module. `api/dependencies.py:748-759 get_knowledge_base_repository` selects between `in_memory` and `object_store` only.

**Outcome:** `PostgresKnowledgeBaseRepository` implementing the full `KnowledgeBaseRepository` protocol; Alembic revision adding `knowledge_bases`, `documents` (with indexed `content_hash` per the existing `O(n) snapshot scan` TODO at `object_store.py:191-193`), and `document_versions` tables; `CHILI_KB_REPOSITORY_BACKEND=postgres` selector wired through `api/dependencies.py:750`; production-mode guardrail (refuse to start in `staging`/`production` when backend resolves to `in_memory`/`object_store`); cross-edge to `database.md` epic 2.

---

## Epic 2: Wire `delete_by_source_document` to the document-delete endpoint

**Gap:** `DELETE /knowledgebases/{kb_id}/documents/{doc_id}` (`api/routers/knowledgebases.py:311-359`) deletes only the object-store payload + the metadata record. It does **not** call `graph_service.delete_by_source_document` or `vector_service.delete_by_source_document`, leaving extracted entities, relationships, and vector points orphaned in the graph and vector store. The cascade only happens on the re-upload (changed-content) path at `routers/knowledgebases.py:432-433`. `architecture.md:780` and `:1369` both call this out explicitly: "delete_by_source_document … is not yet wired to the document-delete endpoint" and "wire `delete_by_source_document` to the document-delete endpoint" is a named next milestone.

**Outcome:** `delete_knowledge_base_document` invokes `graph_service.delete_by_source_document(kb_id, doc_id)` and `vector_service.delete_by_source_document(kb_id, doc_id)` before deleting object-store payloads and the metadata row; a 207-style partial-failure body mirroring the KB-delete cascade for per-step status; pyright + ≥85% coverage on the new failure-path branches; e2e test that registers a document, lets ingestion finish, deletes it, and asserts no orphaned entities/vectors remain.

---

## Epic 3: Verify and harden provenance stamping at every KB write site

**Gap:** `shared/provenance.py:14-39` defines canonical keys/values that **must** be used at every write site that stamps provenance and every read site that filters or deletes by provenance. Cascade deletes (`delete_by_source_document`) depend on every entity and vector point carrying `SOURCE_DOCUMENT_ID_KEY`. There is no enforcement, no shared write helper, and no test that proves every ingestion path (document upload, records ingest, re-upload, future record imports) stamps the full provenance triple (`source_kind`, `source_document_id`, `source_chunk_id`). Architecture §7.3 explicitly ties cascade correctness, audit, and re-ingestion to this contract.

**Outcome:** module-level survey (`backend/ingestion/`, `backend/records/`, `backend/agent/`) confirms every entity/relationship/vector write stamps `shared/provenance.py` keys; a shared `build_provenance(kind, document_id=..., chunk_id=..., feed=..., raw_record_id=...)` helper centralizes construction; contract test in `tests/shared/test_provenance_contract.py` walks every adapter write path and asserts provenance keys are present; cross-edge to `ingestion.md`, `records.md`, `graph.md`.

---

## Epic 4: Strengthen and observe the KB-delete cascade retry path

**Gap:** `handle_knowledge_base_deleted` (`agent/coordinator.py:1702-1731`) retries the 5-step cascade when `cleanup_pending=True`, but: (a) all five calls are issued unconditionally regardless of which originally failed (the 207 body's per-step status is not consulted); (b) no metric or structured log line records per-step outcome on retry; (c) on persistent failure the KB stays in `pending_cleanup=True` forever with no operator surface to inspect or retry manually; (d) there is no maximum-retry budget — failures rely on the DLQ wrapper for backoff. `KbBusyError` blocks mutation while `pending_cleanup=True` (`routers/knowledgebases.py:192-196, 331-335, 387-391`) but offers no escape hatch.

**Outcome:** retry consults the persisted per-step status (requires persisting the 207 body); a `GET /knowledgebases/{id}/cleanup-status` admin endpoint surfaces pending-cleanup state and per-step outcome; `POST /knowledgebases/{id}/cleanup/retry` triggers manual retry; metrics `chili_kb_cleanup_attempts_total{step,outcome}` and structured audit log on every retry; cross-edge to `agent.md` (retry/DLQ contract), `_observability.md`.

---

## Epic 5: Surface KB statistics for the dashboard

**Gap:** `KnowledgeBase` (`shared/types.py:151-165`) carries `entity_count`, `relationship_count`, `document_count`, `status`, `created_at`, `updated_at` — but no `last_ingested_at`, no `last_extraction_at`, no per-type entity histogram, no document-status breakdown, no raw-record count. The Dashboard's KB cards and the SSE `knowledge_base_statuses` snapshot reuse the projection-time numbers from `project_knowledge_base` (`api/_kb_projection.py:24-44`). The existing `# TODO(production): Add domain_config_version: str | None to pin which config version was active. Add owner: str | None and tags: dict[str, str] for organization.` (`shared/types.py:164-165`) flags additional missing surface.

**Outcome:** extend `KnowledgeBase` (or a sibling `KnowledgeBaseSummary`) with `last_ingested_at`, `last_extraction_at`, `entity_type_counts: dict[str, int]`, `document_status_counts: dict[str, int]`, `raw_record_count`; projection persists derived values back through `update_summary`; new `GET /knowledgebases/{id}/statistics` endpoint returns the rich shape; Dashboard card consumes it via TanStack Query; cross-edge to `frontend.md`, `analytics.md`.

---

## Epic 6: Add KB-scoped audit log for create/delete/upload/document-delete

**Gap:** No structured audit-event log exists for KB mutations. `routers/knowledgebases.py` publishes `KnowledgeBaseCreatedEvent` and `KnowledgeBaseDeletedEvent` on the event bus, but these are pipeline-triggering events, not audit events — they have no actor identity, no client IP, no request id, no outcome. `architecture.md` §14.2 lists "Audit log: Track all analyst actions … for compliance" as medium priority. Architecture §7.2 says the API "owns the lightweight KB/document metadata projection" but is silent on audit ownership.

**Outcome:** every KB-router mutation (`create_knowledge_base`, `delete_knowledge_base`, `register_knowledge_base_documents`, `delete_knowledge_base_document`) emits a typed audit-log entry with actor (RBAC principal), action, target KB/document id, outcome, request id, timestamp; a `KbAuditLogRepository` protocol with in-memory + Postgres adapters; admin `GET /knowledgebases/{id}/audit` endpoint with paginated cursor; cross-edge to `_security.md` (cross-cutting audit-log epic), `_observability.md` (structured log shipping).

---

## Epic 7: Add per-KB RBAC (KB-level roles, not only global)

**Gap:** Current authorization on KB routes uses global RBAC roles only: `require_role("analyst")` on create/document-write/document-delete, `require_role("admin")` on KB delete, `require_role("viewer")` on reads (`api/routers/knowledgebases.py:100, 124, 147, 172, 265, 314, 366`). Any global `analyst` can mutate any KB; any global `viewer` can read every KB. Architecture §14.2 names "production IdP profiles + tenant isolation + resource-level authorization" as remaining hardening. No KB-membership concept exists, no per-KB owner field, no per-KB ACL.

**Outcome:** `KbMembershipRepository` protocol storing per-KB role assignments (`owner | editor | viewer`); `require_kb_role(role)` dependency replacing or layering on `require_role` for KB routes; KB-creation auto-grants `owner` to the creator; `POST /knowledgebases/{id}/members` admin endpoint manages membership; in-memory + Postgres adapters; cross-edge to `_security.md` (resource-level authz), `_multitenancy.md` (tenant-scoped membership).

---

## Epic 8: Add tenant-scoped KB namespaces

**Gap:** `KnowledgeBase` has no `tenant_id` field (`shared/types.py:151-165`); `KnowledgeBaseRepository` methods take no tenant context; `api/dependencies.py:748 get_knowledge_base_repository` is `@lru_cache(maxsize=1)` returning a single process-wide repository. There is no notion of per-tenant KB visibility, no tenant filter on `list()`, no tenant column in the (planned) Postgres adapter. Architecture §14.2 lists multi-tenancy as medium priority after auth.

**Outcome:** add `tenant_id: str` to `KnowledgeBase`, `DocumentRecord`, and all protocol methods; tenant context resolved from the request principal (cross-edge to `_security.md` auth middleware); list/get reject cross-tenant access by default; Postgres adapter migration adds `tenant_id NOT NULL` + RLS keyed on `SET LOCAL chili.tenant_id`; cross-edge to `_multitenancy.md`, `database.md` epic 8.

---

## Epic 9: Add KB versioning / point-in-time snapshots

**Gap:** A KB's content evolves continuously — documents are added, re-ingested (re-upload idempotency), and deleted; entities/relationships are upserted as new documents are processed. Nothing today captures a frozen version of the KB at a point in time. There is no `KbSnapshot` model, no `POST /knowledgebases/{id}/snapshots`, no way to query a KB "as of last Monday". Investigation reproducibility (an alert was generated against state X; the analyst needs to see state X) and the dual-graph evolution story (the policy/reference KB needs versioning so claims-KB analytics can pin a policy version) both depend on this.

**Outcome:** `KbSnapshot` model (`snapshot_id`, `kb_id`, `created_at`, `entity_count`, `relationship_count`, `document_count`, `graph_export_key`, `vector_export_key`, `metadata_export_key`, `checksum`); `POST /knowledgebases/{id}/snapshots` (manual + scheduled); read-only `?as_of=<snapshot_id>` query parameter on graph + RAG reads (cross-edge to `graph.md` epic 14 graph snapshot, `vectorstore.md`); retention policy; cross-edge to `analytics.md` (model training pins a snapshot).

---

## Epic 10: Add KB import/export (domain-pack distribution)

**Gap:** No code path exports a portable KB bundle (`KnowledgeBase` metadata + documents + extracted graph + vectors + provenance) or imports one back. Architecture §14.2 lists "Export / reporting: Generate PDF/CSV reports" as low priority but does not name a KB-bundle export. Domain-pack distribution (ship a reference Medicare policy KB, a food-supply-chain reference KB, etc., as a single artifact) requires this, and the dual-graph reference-KB story specifically benefits — the reference KB is otherwise rebuilt per deployment.

**Outcome:** `KbBundle` schema (tarball or zip of: `kb.json`, `documents/`, `graph.jsonl`, `vectors.jsonl`, `provenance.json`, `manifest.json` with checksum + chili version + domain-config version); `POST /knowledgebases/{id}/export` returns a download URL; `POST /knowledgebases/import` accepts a bundle and rebuilds graph + vector + metadata atomically; provenance preserved; cross-edge to `config.md` (domain-pack distribution), `graph.md` epic 14, `storage.md`.

---

## Epic 11: Add cross-KB query primitive (multi-KB investigation)

**Gap:** Reads can already accept `knowledge_base_ids: list[str]` per the dual-graph contract (architecture §7.4), but cross-KB property joining (e.g., matching providers by NPI across a reference policy KB and a claims KB) is "deferred to consumer layers (RAG context builder, UI presentation)" (architecture §7.4). The graph adapter's `query_neighborhood` is single-KB because cross-graph edges are not stored. Investigation Workbench has no UI affordance for spanning multiple KBs beyond the resolved primary + default reference. RAG cannot answer "find all providers flagged in any claims KB whose policy guidance comes from this reference KB."

**Outcome:** decision recorded between (a) explicit cross-KB join API on the graph service (e.g., `find_matching_entities(kb_ids, property_key, property_value)`), (b) a cross-KB index in the vector store keyed on a normalized natural id (NPI, etc.), (c) virtual edges materialized at projection time; chosen approach implemented behind a feature flag; performance budget asserted; cross-edge to `graph.md`, `rag.md`, `frontend.md` (Investigation Workbench multi-KB UI).

---

## Epic 12: Add KB metadata observability and consistency self-check

**Gap:** The KB metadata projection (`api/_kb_projection.py:24-44`) silently writes derived `status`, `entity_count`, `relationship_count` back through the repository on every read. There is no metric on how often the projection actually changed (signal for graph-build event lag), no log line when persisted counts disagree with live graph metrics, no periodic self-check that the repository's `document_count` matches `list_documents(...).total`, and no metric on object-store snapshot size (the `ObjectStoreKnowledgeBaseRepository` JSON blob grows unbounded). Operators have no visibility into projection drift.

**Outcome:** counters `chili_kb_projection_updates_total{field}` and `chili_kb_projection_disagreement_total`; structured log line when projection writes a different value than persisted; periodic `KbMetadataSelfCheck` job comparing `repository.list_documents` count vs persisted `document_count` and graph metrics; metric `chili_kb_metadata_snapshot_bytes` for the object-store adapter's JSON blob; cross-edge to `_observability.md`.

---

## Epic 13: Add document re-upload idempotency edge cases and audit

**Gap:** The re-upload idempotency path (`routers/knowledgebases.py:424-450`) handles the happy path but has open edges: (a) if `graph_service.delete_by_source_document` succeeds and `vector_service.delete_by_source_document` fails, the metadata row + object payload are still deleted, leaving an inconsistent partial state with no `pending_cleanup` flag; (b) the `replaced_document_id` is surfaced only on the receipt — there is no persisted history that document X was replaced by document Y at time T; (c) `repository.get_document_by_content_hash` is O(n) on the object-store snapshot (`object_store.py:191-193` TODO) — collisions across very-large KBs scale poorly; (d) no test covers a concurrent double-upload of the same content (two API workers racing on the same `content_hash`).

**Outcome:** re-upload becomes transactional (all-or-nothing across graph/vector/metadata/object-store) with the same 207 partial-failure surface as KB delete; `document_replacements` history table persisted (`old_id`, `new_id`, `kb_id`, `replaced_at`, `actor`); content-hash lookup uses the indexed Postgres column from epic 1; concurrent-upload test added; cross-edge to `ingestion.md` (transactional ingestion), `_security.md` (replacement audit).

---

## Provisional dependency edges (epic → epic)

- **1** (Postgres adapter) unblocks **5** (statistics needs an indexed column store), **6** (audit log persistence), **7** (membership table), **8** (tenant_id column + RLS), **9** (snapshot history), **13** (indexed content-hash + replacement-history table).
- **3** (provenance audit) unblocks **2** (delete cascade depends on provenance being correctly stamped at write time) and **10** (import/export must round-trip provenance).
- **2** (document-delete cascade wiring) is independent and could land before **1**; it gates a clean **9** (snapshots need consistent cascade behavior) and **13** (re-upload reuses the cascade pattern).
- **4** (cleanup retry hardening) depends on **6** (audit log) for per-step persistence — or stands alone with a smaller surface if persisted independently.
- **7** (per-KB RBAC) depends on **1** (membership repository) and is a prerequisite for **8** (tenant scoping) — though the two can be co-designed.
- **8** (tenant scoping) hard-blocks any multi-tenant deployment story in `_multitenancy.md`.
- **9** (versioning) depends on **graph.md** epic 14 (graph snapshot) and **vectorstore.md** snapshot — cross-module.
- **10** (import/export) depends on **3** (provenance), **9** (snapshot primitive), and `graph.md` epic 14.
- **11** (cross-KB query) is logically independent but pairs with **graph.md** dual-graph hardening and `rag.md` multi-KB retrieval.
- **12** (observability) is independent; pairs with `_observability.md`.
- **13** (re-upload idempotency) depends on **1** (indexed content-hash) and **2** (cascade pattern).

## Cross-cutting fan-out

- → `database.md` epic 2: actual `PostgresKnowledgeBaseRepository` + the schema migration (epic 1).
- → `_security.md`: KB-level audit log (epic 6), per-KB RBAC + ACL (epic 7), document-replacement audit (epic 13).
- → `_multitenancy.md`: `tenant_id` on KB + DocumentRecord + membership (epics 7, 8).
- → `_observability.md`: projection drift metrics, cleanup retry metrics, audit-log shipping (epics 4, 6, 12).
- → `graph.md` epic 14 (snapshot) + `vectorstore.md` snapshot: needed by KB versioning (epic 9) and import/export (epic 10).
- → `ingestion.md`, `records.md`: provenance stamping at every write site (epic 3); transactional re-upload (epic 13).
- → `rag.md`, `frontend.md`: cross-KB query (epic 11), KB picker UX (per the KB entry-points spec, already shipped — Investigation + RAG empty-state CTAs).
- → `config.md`: domain-pack distribution via KB bundle (epic 10).
- → `analytics.md`: KB statistics surface drives the Dashboard cards (epic 5); snapshots pin a state for model training (epic 9).
- → `agent.md`: cleanup retry contract refinement (epic 4) refines the worker DLQ handler.

## Open questions

1. **Postgres-or-defer for KB metadata in v1 multi-user?** Epic 1 introduces a third adapter; `_multitenancy.md` work likely also requires Postgres for tenant isolation. Confirm whether KB metadata moves to Postgres in lockstep with `database.md` epic 2, or whether the object-store adapter remains acceptable for single-tenant production while tenant isolation lands separately. Choice affects whether epics 5/6/7/8/13 wait on epic 1 or can land against the object-store adapter first.
2. **Document-delete cascade failure semantics.** Epic 2 proposes mirroring the KB-delete 207 cascade. Alternative: best-effort fire-and-forget with worker retry only. The 207 surface costs more API code but matches operator mental model. Confirm.
3. **KB-versioning storage strategy.** Epic 9 implies materialized snapshots of graph + vectors per version. Alternative: append-only event log over the graph with time-travel queries (no extra storage but heavy read cost). The decision affects `graph.md` epic 14 framing.
4. **Cross-KB join surface (epic 11).** Three options listed (explicit join API, cross-KB vector index, materialized virtual edges). Each has very different cost/consistency profile. Defer to a follow-up design spec or pick here? Architecture §7.4 explicitly defers this to "consumer layers"; promoting it to a primitive is an architecture-level call.
5. **Per-KB RBAC vs tenant scoping (epics 7 vs 8).** Can roll up tenant scoping into per-KB membership (every KB belongs to one tenant + has a membership ACL) or keep them orthogonal (tenant gates visibility; KB role gates mutation within visibility). The former simplifies; the latter is more flexible.
6. **Audit log ownership (epic 6).** KB-router audit could be: (a) module-owned (`knowledgebases/audit.py` + adapter), (b) cross-cutting (`audit/` module covering all routers, owned by `_security.md`). The choice drives where the protocol/adapters live and whether KB audit ships before the cross-cutting solution.
7. **Statistics endpoint shape (epic 5).** A `GET /knowledgebases/{id}/statistics` endpoint vs enriching `GET /knowledgebases/{id}` itself. Frontend perf vs API tidiness. Confirm whether to break the contract.
