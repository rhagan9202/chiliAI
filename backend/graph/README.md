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

## Dual-Graph Reads

Read-side methods on `GraphServiceProtocol` (`get_entity`, `search_entities`) accept `knowledge_base_ids: list[str]` and span all listed KBs. The API handler boundary uses `shared.kb_scope.resolve_kb_scope(primary, domain_config, kb_repo)` to expand a single primary KB id into the full read scope, auto-attaching the domain's `default_reference_kb_id` (the "policy graph") when configured.

Write methods (`upsert_task`, `update_entity_properties`, `delete_knowledge_base`, `upsert_entities`, `upsert_relationships`) and the neighborhood traversal (`query_neighborhood`, `get_neighbors`) and metrics aggregation (`compute_metrics`) stay scoped to a single KB. Cross-KB joining of distinct entities — e.g., a provider node in claims-KB and the same NPI in policy-KB — is the consumer's responsibility (RAG context builder, UI presentation), not the graph adapter's.
