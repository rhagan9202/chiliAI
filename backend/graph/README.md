# Graph Module

This module provides a graph database abstraction layer for the chiliAI platform, enabling flexible KB storage and retrieval across multiple graph backends.

## Adapters

Graph database implementations are in `adapters/`. Currently supported:
- **InMemoryGraphRepository** — in-process ephemeral graph, no persistence
- **Neo4jGraphRepository** — Neo4j 5.x backend

Each adapter implements the `GraphRepository` protocol in `protocols.py`.

## Neo4j Schema Invariants

The `Neo4jGraphRepository` adapter issues four idempotent schema statements at construction time via `_ensure_schema()`. These power KB-scoped lookups and the path-traversal filter in `get_neighbors`:

- `CREATE CONSTRAINT entity_kb_id_unique` — composite uniqueness on `(:Entity {knowledge_base_id, entity_id})`. Enforces the invariant the rest of the code assumes and provides the composite index used by every entity `MERGE` and lookup.
- `CREATE INDEX entity_kb_id` — single-column index on `(:Entity {knowledge_base_id})` for full-KB scans (`get_entities`, `get_relationships`).
- `CREATE INDEX rel_kb_id_relationship_id` — composite index on `()-[r:RELATES]-()` over `(r.knowledge_base_id, r.relationship_id)`. Powers relationship `MERGE` and lookup. A relationship key constraint would be cleaner but is Neo4j 5.7+ only; this codebase pins the major version only.
- `CREATE INDEX rel_kb_id` — single-column index on `()-[r:RELATES]-()` over `(r.knowledge_base_id)`. Powers the per-hop `kb_id` filter in the variable-length neighborhood traversal.

Each statement uses `IF NOT EXISTS` so re-construction (multiple worker processes, repeated boots) is a no-op. Statement-level failures (e.g. insufficient DDL permission) log a `WARNING` and continue — the queries still work without indexes, just slowly.

To verify the schema is in place against a running Neo4j, use `SHOW INDEXES` and `SHOW CONSTRAINTS` from `cypher-shell`.

## Source-Document Provenance and Cascade Delete

### Provenance metadata

Every `Entity` and `Relationship` upserted through the document pipeline carries provenance metadata so the system knows which document produced it:

| Field | Set by | Meaning |
|-------|--------|---------|
| `source_kind` | ingestion pipeline | `"document"` or `"record"` |
| `source_document_id` | ingestion pipeline | ID of the originating document (SHA-256 of content) |
| `source_chunk_id` | ingestion pipeline | Chunk index within the document |
| `source_feed` | records pipeline | Feed name (records-derived entities only) |
| `source_raw_record_id` | records pipeline | Raw record ID (records-derived entities only) |

### `delete_by_source_document`

`GraphService` and `GraphRepository` expose `delete_by_source_document(kb_id, doc_id)` which removes all entities and relationships whose `source_document_id` matches `doc_id` within the given KB namespace. This is the graph leg of the full KB-delete cascade described in the demo spec at [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](../../docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md).

The full 207 cascade on `DELETE /knowledgebases/{id}` touches: graph (this method), vector store (`delete_by_source_document`), raw records (`delete_by_kb`), object store (payload delete), and the KB repository (metadata delete). A workflow-busy 409 guard prevents deletion while an active pipeline run is in progress.

## Dual-Graph Reads

Read-side methods on `GraphServiceProtocol` (`get_entity`, `search_entities`) accept `knowledge_base_ids: list[str]` and span all listed KBs. The API handler boundary uses `shared.kb_scope.resolve_kb_scope(primary, domain_config, kb_repo)` to expand a single primary KB id into the full read scope, auto-attaching the domain's `default_reference_kb_id` (the "policy graph") when configured.

Write methods (`upsert_task`, `update_entity_properties`, `delete_knowledge_base`, `upsert_entities`, `upsert_relationships`) and the neighborhood traversal (`query_neighborhood`, `get_neighbors`) and metrics aggregation (`compute_metrics`) stay scoped to a single KB. Cross-KB joining of distinct entities — e.g., a provider node in claims-KB and the same NPI in policy-KB — is the consumer's responsibility (RAG context builder, UI presentation), not the graph adapter's.

## Entity Upsert Semantics (`GraphUpsertOptions`, BL-017)

`upsert_entities` / `upsert_relationships` take a trailing `options: GraphUpsertOptions | None = None` (`graph/models.py`). Defaults preserve today's behavior for existing callers that pass no options.

- **`merge_mode`** (`"merge_properties"` default, or `"replace_properties"`): on update, `merge_properties` does a shallow dict merge of the incoming `properties`/`metadata` over the stored record (explicit `None` values overwrite, since they're present keys in the incoming dict); `replace_properties` reproduces the pre-BL-017 blind-overwrite.
- **Adapter-owned `version`**: the incoming payload's `version` field is always ignored. New entities always start at `version=1`. On update, `version` increments only when merged `properties` or `type` differ from what's stored — a `metadata`-only change still writes the updated record but leaves `version` untouched, and replaying an identical payload is a true no-op.
- **`expected_version` conflict pre-pass**: when set, the adapter validates every entity/relationship in the batch against the stored `version` *before* writing anything; a mismatch raises `GraphVersionConflictError(entity_id, expected_version, actual_version)` (`graph/exceptions.py`) and the whole batch is left untouched (no partial writes).
- **`integrity_mode`** (`"strict"` default, or `"create_placeholders"`) — relationship upserts only: `strict` raises `GraphIntegrityError` if any relationship references a `source_id`/`target_id` not already present in the KB; `create_placeholders` is reserved for a future task and is not yet implemented by any adapter (falls through to `strict` semantics today).

**Status by adapter:** `InMemoryGraphRepository.upsert_entities` (BL-017 Task 2) and `InMemoryGraphRepository.upsert_relationships` (BL-017 Task 3) implement merge/version/integrity semantics in full. `Neo4jGraphRepository.upsert_entities` implements merge/version semantics via an atomic read-modify-write — one `MATCH` read followed by one `MERGE` write, both run through the caller's active transaction when `repository.transaction(kb)` is open (BL-017 Task 4). `Neo4jGraphRepository.upsert_relationships` still accepts `options` for protocol-signature compatibility but does not yet act on it — it blind-overwrites (Neo4j relationship parity lands in BL-017 Task 5).
