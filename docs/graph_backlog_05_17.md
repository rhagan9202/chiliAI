# Graph Production Readiness Backlog - 2026-05-17

## Scope

This backlog covers the remaining work to move `backend/graph` from a typed, tested graph persistence module into a production-ready graph subsystem.

Current baseline:

- `graph` and `tests/graph` are included in backend pyright strict scope.
- The graph service supports document-pipeline upserts through `GraphService.upsert_task()`.
- The graph service supports structured-record upserts through `GraphService.upsert_records_graph()` without document artifacts or `GraphUpdatedEvent` publication.
- In-memory and Neo4j repository adapters support entity/relationship upserts, neighborhood reads, entity search, entity property updates, metrics counts, and KB/entity/relationship deletion.
- KB deletion calls into graph namespace cleanup through `GraphService.delete_knowledge_base()`.

Primary remaining gaps:

- Repository upserts do not consistently enforce referential integrity or production-grade merge/version semantics.
- Graph writes are only partially idempotent: stable IDs overwrite data, but there is no change detection, version conflict detection, write idempotency key, or replay audit.
- Filtered subgraph reads, relationship detail reads, cursor pagination, and richer investigation/RAG query surfaces are not first-class service methods yet.
- Document-level graph cleanup depends on provenance work outside the graph module and is not implemented as a graph service workflow.
- Neo4j production hardening is incomplete: constraints/indexes, retry/backoff, schema bootstrap, session observability, and live operational checks need to be explicit.
- Graph metrics are basic counts and average degree; production analytics needs richer metrics and efficient backend-native computation.

## Priority Map

| Priority | Story | Why It Matters |
| --- | --- | --- |
| P0 | Stories 1-4 | Protect graph correctness under replay, bad relationships, and partial failures. |
| P0 | Stories 5-6 | Support deletion/reindex flows and document provenance cleanup. |
| P1 | Stories 7-11 | Complete production query surfaces for investigation, RAG, analytics, and UI. |
| P1 | Stories 12-15 | Harden Neo4j operations, security, observability, and scaling. |
| P2 | Stories 16-18 | Add advanced graph metrics, multi-adapter certification, and docs/config completion. |

---

## Story 1: Enforce Referential Integrity On Relationship Upserts

**As a graph operator**, I need relationship writes to fail when endpoints do not exist, so the graph does not accumulate dangling edges or implicit placeholder nodes.

**Current State**

- `InMemoryGraphRepository.upsert_relationships()` stores relationships even when `source_id` or `target_id` is missing.
- `Neo4jGraphRepository.upsert_relationships()` uses `MERGE` for source and target nodes, which can create endpoint nodes without type/properties.
- `backend/graph/adapters/in_memory.py` explicitly calls out referential integrity as a production TODO.

**Implementation Notes**

- Add a repository-level policy for relationship endpoint handling:
  - `strict`: reject missing endpoints.
  - `create_placeholder`: only allowed for explicitly configured legacy/import flows.
- Make `strict` the production default.
- Add a typed `GraphIntegrityError` that includes KB id, relationship id, source id, and target id without leaking payload content.
- For Neo4j, replace endpoint `MERGE` in relationship writes with endpoint `MATCH` under strict mode.
- Preserve structured-records behavior by ensuring record mapping upserts entities before relationships.

**Acceptance Criteria**

- In strict mode, in-memory relationship upsert fails if either endpoint is missing.
- In strict mode, Neo4j relationship upsert does not create missing endpoint nodes.
- `GraphService.upsert_task()` and `upsert_records_graph()` surface a typed graph error on missing endpoints.
- Existing valid relationship upserts continue to pass.
- Tests cover missing source, missing target, both missing, and valid endpoints for both adapters.
- `pyright`, `ruff`, and graph tests pass.

---

## Story 2: Add Merge Semantics And Version Conflict Detection

**As a data steward**, I need entity and relationship upserts to merge updates intentionally instead of blindly overwriting existing graph state.

**Current State**

- In-memory entity upsert overwrites the stored entity object.
- Neo4j entity upsert replaces `properties_json`, `metadata_json`, `updated_at`, and `version`.
- `update_entity_properties()` merges properties, but normal upsert does not expose merge strategy.
- There is no optimistic version conflict detection.

**Implementation Notes**

- Add `GraphUpsertOptions` or equivalent service/repository options:
  - `merge_properties`
  - `replace_properties`
  - `merge_metadata`
  - `expected_version`
- Default production writes should merge metadata/provenance and use version increments.
- Reject stale writes when `expected_version` is lower than the stored version.
- Keep deterministic replay safe: replaying identical payload should not increment version.

**Acceptance Criteria**

- Upserting a changed entity with merge mode preserves unspecified existing properties.
- Upserting a changed entity with replace mode removes unspecified existing properties.
- Replaying an identical entity payload is a no-op and does not increment version.
- A stale `expected_version` raises a typed conflict error.
- Relationship property and weight updates follow the same merge/version rules.
- Tests cover in-memory and Neo4j behavior.

---

## Story 3: Add Change Detection And Idempotent Graph Update Receipts

**As a pipeline operator**, I need event replay to be safe and visible, so duplicate graph work does not generate misleading downstream work.

**Current State**

- `GraphService.upsert_task()` always writes a graph update artifact and publishes `GraphUpdatedEvent` after successful repository writes.
- Stable entity and relationship IDs make writes idempotent at storage level, but there is no change detection.
- Downstream analytics and embeddings can be triggered even when the graph did not materially change.

**Implementation Notes**

- Compute content fingerprints for incoming entities and relationships.
- Store last applied fingerprint per graph object.
- Add `created`, `updated`, `unchanged`, and `deleted` counts to graph upsert results.
- Publish `GraphUpdatedEvent` only when configured:
  - always publish for audit mode.
  - publish on change only for production default.
- Persist replay metadata with correlation id and source validation report id.

**Acceptance Criteria**

- Replaying the same `GraphBuildTask` reports unchanged objects.
- Replaying the same task does not trigger downstream event publication in change-only mode.
- Mutating one entity triggers an update count of one and publishes a graph update.
- Receipts distinguish created, updated, and unchanged counts.
- Tests cover replay, partial change, full change, and audit-mode always-publish behavior.

---

## Story 4: Make Batch Upserts Atomic At Task Scope

**As an operator**, I need graph build tasks to avoid partially applied state when a later entity or relationship batch fails.

**Current State**

- `GraphService` opens a repository transaction per entity batch and per relationship batch.
- A failure in a later batch can leave prior batches committed.
- `BatchUpsertError` reports successful counts after partial success, but the task is not atomic.

**Implementation Notes**

- Add a repository capability for task-scoped transactions.
- Use a single transaction for the full graph task when the adapter supports it.
- For adapters that cannot hold a task-size transaction, add compensating cleanup or explicit partial-success mode.
- Keep chunking for memory/performance, but write chunks inside the same transaction when possible.

**Acceptance Criteria**

- A failure in any entity or relationship batch rolls back the full task for transaction-capable adapters.
- Partial-success mode is opt-in and clearly recorded in the receipt/error.
- In-memory adapter tests prove rollback restores entities, relationships, and adjacency indexes.
- Neo4j tests prove rollback is called when a relationship batch fails.
- `BatchUpsertError` includes enough metadata to diagnose stage and batch index.

---

## Story 5: Add Document-Level Graph Cleanup

**As a KB maintainer**, I need removing a document to remove or detach graph objects derived only from that document.

**Current State**

- KB-level graph namespace deletion exists.
- Architecture docs state document-level graph/vector cleanup remains future work until provenance-backed delete semantics are implemented.
- `GraphService` has no `delete_source_document()` or provenance-aware cleanup method.

**Implementation Notes**

- Use ingestion provenance metadata on entities/relationships to track source document ids and validation report ids.
- Add service method:
  - `delete_source_document_graph(knowledge_base_id, source_document_id)`
- Delete graph objects derived exclusively from the source document.
- For shared/canonical entities backed by multiple documents, remove only that document provenance and keep the entity.
- Cascade relationship deletion when either endpoint is deleted or when relationship provenance is removed entirely.

**Acceptance Criteria**

- Deleting a document removes entities that only came from that document.
- Deleting a document preserves entities with provenance from other documents.
- Relationship cleanup handles endpoint deletion and relationship-only provenance correctly.
- Cleanup is idempotent under retries.
- Tests cover one-document entities, shared entities, relationships, missing document ids, and replayed cleanup events.

---

## Story 6: Add Reindex And Replacement Workflows

**As an operator**, I need to reprocess or replace graph data for a document without creating duplicates or stale relationships.

**Current State**

- Graph upsert paths are incremental and ID-based.
- There is no graph service workflow for reindexing a document or replacing all graph objects associated with a validation report.

**Implementation Notes**

- Add graph lifecycle operations:
  - replace graph outputs for `source_document_id`
  - replace graph outputs for `validation_report_id`
  - mark old graph outputs superseded
- Use provenance and object fingerprints to identify old derived objects.
- Make replacement atomic at task scope.

**Acceptance Criteria**

- Reindexing the same document replaces stale entities and relationships.
- Removed entities from the new extraction are deleted or superseded.
- Unchanged entities are preserved without version churn.
- Reindex emits a clear changed/unchanged/deleted receipt.
- Tests cover entity removal, relationship removal, unchanged replay, and changed replacement.

---

## Story 7: Add Filtered Subgraph Reads

**As an investigator**, I need to request a subgraph by a known set of entity IDs so the UI and RAG pipeline can inspect a focused evidence slice.

**Current State**

- `GraphServiceProtocol` and `GraphService` TODOs call out `get_subgraph(kb_id, entity_ids)`.
- Repository adapters expose neighborhood reads, not arbitrary filtered subgraph reads.

**Implementation Notes**

- Add `get_subgraph(knowledge_base_id, entity_ids, include_internal_relationships=True)`.
- Return all requested entities plus relationships where both endpoints are in the result set.
- Add optional expansion depth for one-hop context if needed by RAG/UI.
- Implement in both in-memory and Neo4j adapters.

**Acceptance Criteria**

- Requesting entity IDs returns exactly those entities that exist.
- Internal relationships between returned entities are included.
- Relationships to non-requested entities are excluded unless expansion is requested.
- Missing entity IDs are reported in metadata or ignored deterministically.
- Tests cover empty IDs, missing IDs, internal edges, external edges, and expansion behavior.

---

## Story 8: Add Relationship Detail Reads And Pagination

**As a UI/API consumer**, I need graph reads to support relationship detail views and pagination for large graphs.

**Current State**

- Repository TODO mentions `get_relationship()` and pagination for `get_entities()`/`get_relationships()`.
- `get_entities()` and `get_relationships()` return full lists.
- API graph router currently exposes only entity detail.

**Implementation Notes**

- Add repository methods:
  - `get_relationship(kb_id, relationship_id)`
  - `list_entities(kb_id, limit, cursor/offset, filters)`
  - `list_relationships(kb_id, limit, cursor/offset, filters)`
- Keep existing methods as compatibility wrappers if needed.
- Add service models for paged graph reads.
- Add API routes after service behavior is tested.

**Acceptance Criteria**

- Relationship detail lookup returns source id, target id, type, properties, weight, and provenance metadata.
- Entity and relationship list methods enforce limits and stable ordering.
- Pagination is deterministic under repeated reads.
- Neo4j queries use `SKIP/LIMIT` or cursor-safe alternatives with documented tradeoffs.
- Tests cover first page, second page, empty page, filtering by type, and invalid limits.

---

## Story 9: Improve Entity Search Quality And Indexing

**As an analyst**, I need entity search to find relevant graph entities quickly across names, identifiers, and configured display fields.

**Current State**

- In-memory search scans string property values.
- Neo4j search uses `toLower(coalesce(entity.properties_json, "")) CONTAINS`.
- Search does not expose total count, match fields, rank, highlighting, or type filters at the service level.

**Implementation Notes**

- Add search request model with query, entity types, property filters, limit, offset/cursor, and KB id.
- Use configured display/title fields when available.
- Add Neo4j full-text index or property indexes for selected searchable fields.
- Return search hits with rank, matched fields, and optional snippets.

**Acceptance Criteria**

- Search can filter by entity type.
- Search matches configured display fields and stable identifier fields.
- Results include deterministic ordering and a total or next cursor.
- Blank or too-short queries return a safe empty result.
- Neo4j full-text/index setup is idempotent.
- Tests cover rank ordering, type filters, identifier search, and pagination.

---

## Story 10: Add Backend-Native Graph Metrics

**As an analytics consumer**, I need graph metrics that are accurate and efficient on large graphs.

**Current State**

- `GraphService.compute_metrics()` returns entity count, relationship count, and average degree.
- Repository TODO mentions richer metrics such as degree centrality and PageRank.
- Counts are backend reads, but advanced metrics are not implemented.

**Implementation Notes**

- Add metrics model for:
  - degree distribution
  - top entities by degree
  - connected component count
  - isolated entity count
  - optional PageRank/centrality where backend supports it
- Implement exact low-cost metrics first.
- Add feature flags for expensive metrics.
- For Neo4j, use Cypher aggregation and optional Graph Data Science integration only when configured.

**Acceptance Criteria**

- Metrics API returns existing counts plus top-degree and isolated entity counts.
- Expensive metrics are disabled unless enabled by config.
- Metrics queries are scoped by KB id.
- Tests cover empty graph, simple chain, disconnected graph, and cyclic graph.
- Large graph metric tests run within an agreed performance budget.

---

## Story 11: Add Graph Query Authorization And Tenant Isolation Checks

**As a security owner**, I need graph reads and writes to enforce KB scoping, RBAC, and tenant isolation consistently.

**Current State**

- Graph repository methods take `knowledge_base_id`.
- API routes use role dependencies in some places.
- There is no graph-level policy object that validates tenant access before service operations.

**Implementation Notes**

- Add service-boundary authorization hooks or policy checks for KB access.
- Ensure every API graph route obtains KB id from an authorized context.
- Add tenant id to graph metadata if/when tenancy lands.
- Add default-deny behavior in production mode when auth is enabled but KB access context is missing.

**Acceptance Criteria**

- Graph service/API calls cannot query a KB without authorized KB access.
- Tests cover viewer read, analyst read, unauthorized read, and cross-KB isolation.
- Repository-level KB scoping remains enforced even when service checks are bypassed in tests.
- Security failures are logged without exposing graph payloads.

---

## Story 12: Add Neo4j Constraints, Index Bootstrap, And Health Checks

**As an operator**, I need Neo4j schema constraints and health checks to be created and verified before production traffic.

**Current State**

- Neo4j adapter writes nodes with label `Entity` and relationships with type `RELATES`.
- There is no explicit schema bootstrap for uniqueness constraints or search indexes.
- Health checking is outside the graph adapter.

**Implementation Notes**

- Add idempotent schema setup:
  - uniqueness constraint on `(knowledge_base_id, entity_id)`
  - relationship lookup index on `(knowledge_base_id, relationship_id)`
  - indexes for entity type and searchable properties
- Add `check_health()` or graph-specific health service.
- Validate Neo4j database connectivity, schema status, and write/read readiness.

**Acceptance Criteria**

- Schema bootstrap can run repeatedly without errors.
- Missing required constraints are reported by health checks.
- Production startup can fail fast when required schema is missing.
- Tests verify generated Cypher for constraints/indexes.
- Optional live Neo4j integration test verifies bootstrap against a real database when env vars are present.

---

## Story 13: Add Neo4j Retry, Timeout, And Error Classification

**As an operator**, I need transient Neo4j failures to retry safely and persistent failures to fail clearly.

**Current State**

- Neo4j adapter catches `Neo4jError` and wraps it as `GraphPersistenceError`.
- There is no retry/backoff, timeout config, or error classification.

**Implementation Notes**

- Add graph DB config for read/write timeout, retry count, and retry backoff.
- Retry transient errors for idempotent reads and safe upserts.
- Do not retry validation/integrity errors.
- Preserve original exception class in metadata or logs without leaking secrets.

**Acceptance Criteria**

- Transient write failures retry according to config.
- Permanent integrity errors do not retry.
- Timeouts are applied to sessions/transactions where supported.
- Tests use fake Neo4j exceptions to verify retry and non-retry paths.
- Logs include operation name, KB id, attempt number, and safe error class.

---

## Story 14: Add Graph Observability And Audit Logging

**As an operator**, I need graph writes, reads, deletes, and failures to be observable.

**Current State**

- Graph service does not emit module-specific metrics or structured audit logs.
- Worker-level tracing exists elsewhere, but graph operations do not have dedicated spans/metrics.

**Implementation Notes**

- Add metrics:
  - graph entities upserted
  - relationships upserted
  - unchanged objects
  - graph write duration
  - graph read duration
  - graph errors by operation
  - deletes by scope
- Add structured audit logs for write/delete operations.
- Add trace spans around repository operations and artifact/event publication.
- Avoid logging entity properties unless explicitly redacted/allowed.

**Acceptance Criteria**

- Successful upserts emit counts and duration metrics.
- Failed upserts emit safe error metrics.
- Deletes emit audit logs with KB id, scope, and object counts.
- Tests or smoke checks verify no raw sensitive property values appear in logs.
- Operational docs list metric names and labels.

---

## Story 15: Add Graph Snapshot Export And Restore

**As a platform operator**, I need to export and restore graph state for backups, migrations, and offline investigation.

**Current State**

- Repositories expose reads, but there is no snapshot artifact format or restore workflow.
- Analytics modules consume graph snapshots through separate in-memory source abstractions.

**Implementation Notes**

- Define `GraphSnapshot` model with KB id, entities, relationships, schema version, created_at, and checksum.
- Add service methods:
  - `export_snapshot(knowledge_base_id)`
  - `restore_snapshot(snapshot, mode)`
- Restore modes:
  - replace KB graph
  - merge into KB graph
  - validate-only
- Persist snapshots to object storage for long-running operations.

**Acceptance Criteria**

- Snapshot export includes all entities and relationships for a KB.
- Snapshot checksum changes when graph content changes.
- Replace restore clears old graph data before restoring.
- Validate-only restore reports missing endpoints and schema/version issues without writing.
- Tests cover export, replace restore, merge restore, invalid relationship, and checksum stability.

---

## Story 16: Add Production Adapter Certification Tests

**As a release owner**, I need the in-memory and Neo4j adapters to pass the same behavioral contract.

**Current State**

- In-memory and Neo4j tests exist, including optional live Neo4j integration tests.
- There is no single reusable contract suite that every graph repository adapter must pass.

**Implementation Notes**

- Create adapter contract tests for:
  - entity upsert/read/update
  - relationship upsert/read
  - referential integrity
  - neighborhood traversal
  - filtered subgraph
  - search
  - pagination
  - metrics
  - delete/reindex
  - transaction rollback
- Run contract tests against in-memory by default.
- Run the same contract against Neo4j when `NEO4J_TEST_URI` and credentials are present.

**Acceptance Criteria**

- Adding a new graph adapter requires passing the contract suite.
- In-memory and Neo4j behavior are consistent for all contract cases.
- Optional Neo4j tests skip cleanly when env vars are absent.
- CI has a fast adapter contract job and a documented live Neo4j job.

---

## Story 17: Complete Graph Configuration And Documentation

**As an engineer deploying chiliAI**, I need graph behavior to be configured and documented without reading source code.

**Current State**

- `GraphDbConfig` selects backend, URI, pool size, and auth env var.
- Production behavior such as strict referential integrity, retries, schema bootstrap, query limits, metrics mode, and full-text search is not fully represented in config.
- Architecture docs mention some future cleanup and graph read gaps.

**Implementation Notes**

- Extend `GraphDbConfig` with production options:
  - integrity mode
  - schema bootstrap mode
  - retry policy
  - read/write timeout
  - max traversal depth
  - default page size and max page size
  - search mode
  - expensive metrics enabled flag
- Update default domain configs.
- Update architecture/onboarding docs.
- Document local, dev, and production graph deployment profiles.

**Acceptance Criteria**

- All production graph behavior introduced by this backlog is configurable or explicitly documented as fixed.
- Config validation rejects unsafe production combinations.
- Default configs validate.
- Docs include Neo4j setup, required constraints, auth env var format, and test commands.
- Stale TODO inventory entries are updated when stories are completed.

---

## Story 18: Add Production Graph Release Gate

**As a release owner**, I need one command that proves graph production readiness before promotion.

**Current State**

- Unit tests cover many graph behaviors.
- Optional live Neo4j integration tests exist.
- There is no named production certification target for graph.

**Implementation Notes**

- Add a documented gate command that runs:
  - pyright
  - ruff
  - graph unit tests
  - adapter contract tests
  - optional live Neo4j tests
  - migration/schema bootstrap checks
  - performance smoke tests for large graph reads/writes
- Record expected runtime and required environment variables.

**Acceptance Criteria**

- A single documented command runs the fast graph gate locally.
- A separate documented command runs live Neo4j certification.
- Gate fails on pyright errors, ruff errors, contract failures, missing constraints, or performance smoke regressions.
- CI can run fast gates on every PR and live Neo4j gates on scheduled/pre-release jobs.
- Release notes can link to the generated graph certification output.

---

## Suggested Execution Order

1. Story 1: referential integrity.
2. Story 2: merge/version conflict semantics.
3. Story 3: change detection and idempotent receipts.
4. Story 4: task-scoped atomicity.
5. Story 7: filtered subgraph reads.
6. Story 8: relationship reads and pagination.
7. Story 9: search quality and indexing.
8. Story 5: document-level cleanup.
9. Story 6: reindex/replacement workflows.
10. Story 12: Neo4j constraints and health checks.
11. Story 13: Neo4j retry/timeout/error classification.
12. Story 14: observability and audit logs.
13. Story 10: backend-native graph metrics.
14. Story 11: graph authorization and tenant isolation.
15. Story 15: snapshot export/restore.
16. Story 16: adapter certification tests.
17. Story 17: configuration and docs.
18. Story 18: production release gate.

## Production Readiness Definition

The graph module should be considered production-ready only when:

- Relationship writes cannot create dangling or unintended endpoint nodes in production mode.
- Upserts are idempotent under event replay and report created/updated/unchanged/deleted outcomes.
- Graph build tasks are atomic or explicitly marked as partial-success with recovery guidance.
- Document deletion and reindex workflows clean graph outputs using provenance.
- Investigation, RAG, and analytics consumers have paginated, filtered, efficient graph read APIs.
- Neo4j schema constraints, indexes, retries, timeouts, and health checks are explicit and tested.
- Graph operations emit safe logs, metrics, and traces.
- In-memory and Neo4j adapters pass a shared behavioral contract suite.
- The graph production certification gate passes in CI.
