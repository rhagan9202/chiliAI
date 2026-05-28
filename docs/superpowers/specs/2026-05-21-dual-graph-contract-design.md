# Dual-Graph Contract Design

## Goal

Enable an analyst's read against a transactional ("claims") knowledge base to transparently include a domain-level reference ("policy") knowledge base in the same query, without requiring per-request UI plumbing or storage-layer restructuring. Writes stay scoped to a single KB. The mechanism is a small, composable contract change at the protocol layer: read methods accept `kb_ids: list[str]` instead of `kb_id: str`, and the API handler boundary uses a tiny resolver to expand the active primary KB into the full read scope based on domain configuration.

This is the protocol-level foundation for the dual-graph architecture (Option E from prior brainstorming). It does NOT create or populate a policy KB, does NOT introduce cross-KB property joining at the adapter level, and does NOT change writes.

## Current Context

`backend/graph/protocols.py`, `backend/vectorstore/protocols.py`, and `backend/rag/protocols.py` define service boundaries where every read carries a single `knowledge_base_id: str`. The Neo4j and Qdrant adapters scope queries via a `knowledge_base_id` property filter on every node and embedding. The recently-landed schema-index work (commit `21d43b7`) added composite indexes on `(:Entity {knowledge_base_id, entity_id})` and on `:RELATES` relationships, so the Neo4j adapter is ready for `WHERE entity.knowledge_base_id IN $kb_ids` queries (the composite-index leading-column principle covers the multi-value case efficiently).

The Pydantic `DomainConfig` model (`backend/config/schema.py` line 341) currently has no fields that describe KB granularity. KB membership is a runtime concern: KBs are created via `POST /knowledgebases` and the analyst selects one in the UI before running a query.

The `KnowledgeBaseRepository` protocol in `backend/knowledgebases/protocols.py` exposes `get(knowledge_base_id: str) -> KnowledgeBase | None` — sufficient for existence checks at scope resolution time.

The existing KB `kb-1` ("Fraud KB") is a transactional KB seeded with synthetic DE-SynPUF data. After this change it remains a transactional KB. No data migration is required.

## Scope

In scope:

- One new optional field on `DomainConfig`: `default_reference_kb_id: str | None`.
- One new module: `backend/shared/kb_scope.py` exporting `resolve_kb_scope(primary_kb_id, domain_config, kb_repository) -> list[str]`.
- Read-method signature changes on `GraphServiceProtocol`, `VectorServiceProtocol`, `RagServiceProtocol` and their request/response models.
- Adapter implementations updated to use `WHERE knowledge_base_id IN $kb_ids` (Cypher) or equivalent (Qdrant filter `match: {any: ...}`, in-memory dict membership).
- API handler call sites that invoke read paths: each calls the resolver once and passes the resulting list to the service.
- Tests for the resolver (pure-function unit tests), for multi-KB query behavior in each adapter, and for the soft-fail path when the configured reference KB does not exist.

Out of scope:

- Creating, ingesting, or populating a policy KB.
- Reference-data feed configs (NPI directory, OIG LEIE exclusion list, CPT/HCPCS codesets).
- Cross-KB property joining at the adapter level. Distinct entities are returned across listed KBs; any merging (e.g., dedupe by NPI for providers) happens at consumer layers (RAG context builder, UI presentation).
- Changes to write methods, KB management endpoints, or the existing KB metadata schema.
- Per-request opt-out (`include_reference=false` query param) — YAGNI; can be added later if a real use case emerges.
- Multi-reference support (more than one reference KB per domain). The single-field shape is intentional for v1.

## Design

### 1. Domain config addition

In `backend/config/schema.py`, extend `DomainConfig`:

```python
class DomainConfig(BaseModel):
    # ... existing fields unchanged ...

    default_reference_kb_id: str | None = Field(
        default=None,
        description=(
            "ID of a knowledge base that is auto-attached to every read in this domain "
            "(the 'policy graph'). When None, dual-graph behavior is disabled and reads "
            "scope to the primary KB only."
        ),
    )
```

No validator runs against the KB store — referencing a non-existent KB is detected at request time by the resolver (see §2).

### 2. Scope resolver

New module `backend/shared/kb_scope.py`:

```python
"""Resolve a primary KB id into the full read scope for the domain."""

from __future__ import annotations

import logging
from typing import Protocol

from config.schema import DomainConfig

logger = logging.getLogger(__name__)


class KnowledgeBaseExistenceCheck(Protocol):
    """Minimal protocol the resolver uses to verify a reference KB exists."""

    def get(self, knowledge_base_id: str) -> object | None: ...


def resolve_kb_scope(
    primary_kb_id: str,
    domain_config: DomainConfig,
    kb_repository: KnowledgeBaseExistenceCheck,
) -> list[str]:
    """Return the list of KB IDs that reads should span for this request.

    - If the domain has no default_reference_kb_id, returns [primary].
    - If the primary IS the reference KB (e.g. the analyst is querying the policy
      KB itself), returns [primary] only — no self-attach loop.
    - If the reference KB is configured but doesn't exist, logs a WARNING and
      returns [primary] only. The app keeps running with degraded behavior.
    - Otherwise returns [primary, reference] in that order.
    """
    reference_id = domain_config.default_reference_kb_id
    if reference_id is None:
        return [primary_kb_id]
    if reference_id == primary_kb_id:
        return [primary_kb_id]
    if kb_repository.get(reference_id) is None:
        logger.warning(
            "Configured default_reference_kb_id=%r does not exist; "
            "falling back to primary-only scope (primary=%r)",
            reference_id,
            primary_kb_id,
        )
        return [primary_kb_id]
    return [primary_kb_id, reference_id]
```

The resolver:
- Is a pure function (modulo the existence check) — easy to unit test.
- Takes a `KnowledgeBaseExistenceCheck` minimal protocol so tests don't need a full `KnowledgeBaseRepository`.
- Logs the WARNING at module-level logger `shared.kb_scope`.
- Returns ordering with primary first — useful for downstream consumers that want to know "which result came from the primary KB" (they can match on index).

### 3. Read-method signature changes

#### 3a. Graph protocol (`backend/graph/protocols.py`)

| Method | Read or write? | Change |
|---|---|---|
| `upsert_task(task)` | write | unchanged (task carries scalar kb_id) |
| `get_entity(kb_id, entity_id)` | read | `kb_id: str` → `knowledge_base_ids: list[str]` |
| `update_entity_properties(kb_id, ...)` | write | unchanged |
| `query_neighborhood(kb_id, entity_id, depth)` | read | **unchanged** — traversal is inherently single-graph; cross-KB joining happens at consumer layers |
| `search_entities(kb_id, query, limit, offset)` | read | `kb_id: str` → `knowledge_base_ids: list[str]` |
| `compute_metrics(kb_id)` | read but aggregate | **unchanged** — per-KB metric semantics |
| `delete_knowledge_base(kb_id)` | write | unchanged |

`query_neighborhood` stays single-KB because relationships are anchored within one graph; the dual-graph model deliberately does NOT store cross-KB edges. If an analyst needs to see whether a provider in the claims neighborhood is on the exclusion list in the policy graph, the post-processing layer does that match by shared property (NPI) — not the graph traversal.

`compute_metrics` stays single-KB because mixing claims and policy stats produces meaningless aggregates ("how many entities are in this KB?" is per-KB).

#### 3b. Vector store protocol (`backend/vectorstore/protocols.py` + service models)

| Model / method | Read or write? | Change |
|---|---|---|
| `VectorIndexSubmission` | write | unchanged |
| `VectorIndexRequest.knowledge_base_id: str` | write | unchanged |
| `VectorIndexReceipt.knowledge_base_id: str` | write | unchanged |
| `VectorSearchRequest.knowledge_base_id: str` | read | `→ knowledge_base_ids: list[str]` |
| `VectorSearchResponse.knowledge_base_id: str` | read response | `→ knowledge_base_ids: list[str]` to mirror the request |
| `VectorServiceProtocol.index(request)` | write | unchanged |
| `VectorServiceProtocol.search(request)` | read | request shape changes — protocol signature itself stays |

#### 3c. RAG protocol (`backend/rag/protocols.py` + service models)

| Model / method | Change |
|---|---|
| `RagQueryRequest.knowledge_base_id: str` | `→ knowledge_base_ids: list[str]` |
| `RagQueryResponse.knowledge_base_id: str` | `→ knowledge_base_ids: list[str]` to mirror request |
| `RagServiceProtocol.answer_question(*, knowledge_base_id: str, question)` | `→ knowledge_base_ids: list[str]` |
| `RagServiceProtocol.answer(request)` | request shape changes; protocol unchanged |
| `RagServiceProtocol.stream_answer(request)` | request shape changes; protocol unchanged |

### 4. Adapter implementations

#### 4a. Neo4j graph adapter

Affected queries: `get_entity`, `search_entities` (any read with multi-KB scope). Change `WHERE entity.knowledge_base_id = $knowledge_base_id` to `WHERE entity.knowledge_base_id IN $knowledge_base_ids`. The composite index `(:Entity {knowledge_base_id, entity_id})` covers `kb_id IN list` queries by leading-column principle (Cypher planner uses the same index for `IN` membership as for `=`).

`query_neighborhood` and `compute_metrics` are unchanged.

#### 4b. In-memory graph adapter

Internal storage already keys entities/relationships by `(kb_id, entity_id)`. Change list-iteration filters to `if entity.knowledge_base_id in kb_ids` (set/list membership). No data structure change.

#### 4c. Qdrant vector adapter

Search filter:

```python
# before
filter=Filter(must=[FieldCondition(key="kb_id", match=MatchValue(value=kb_id))])

# after
filter=Filter(must=[FieldCondition(key="kb_id", match=MatchAny(any=kb_ids))])
```

Qdrant supports `MatchAny` natively — single round-trip, server-side filtering. The collection layout (which payload fields are indexed) does not change.

#### 4d. In-memory vector adapter

Simple list filter: `if record.knowledge_base_id in kb_ids`.

### 5. API handler boundary

Each read endpoint adds three lines:

```python
@router.get("/{knowledge_base_id}/entities/{entity_id}")
def get_entity_route(
    knowledge_base_id: str,
    entity_id: str,
    domain_config: DomainConfig = Depends(get_domain_config),
    kb_repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
) -> EntityResponse:
    kb_ids = resolve_kb_scope(knowledge_base_id, domain_config, kb_repository)
    entity = graph_service.get_entity(kb_ids, entity_id)
    # ... existing response shaping ...
```

The `knowledge_base_id` path/query parameter stays. The resolver is called once per request. No new endpoints, no new request payload fields, no new auth surface.

Write endpoints are not modified.

### 6. Migration

No data migration is required.

- Existing kb-1 ("Fraud KB") remains a transactional KB with no reference KB attached. Reads continue to operate on `[kb-1]` exactly as today.
- The `default_reference_kb_id` field defaults to `None` on every existing domain config file.
- The behavior change is opt-in: the analyst (a) creates a new KB intended as the policy graph, (b) ingests reference data into it via the standard ingestion pipeline, (c) edits the domain config to set `default_reference_kb_id` to that KB's id.
- A future "policy KB creation" workflow (UI button, CLI, or automatic provisioning on domain load) is out of scope of this contract change.

### 7. Behavior when reference KB equals primary

If the analyst is querying against the policy KB directly (e.g., examining the exclusion list or browsing codesets), the resolver returns `[primary]` only — no self-attach loop, no duplicate result sets, no Cypher `IN [x, x]`. This is the `primary_kb_id == reference_id` branch in §2.

### 8. Behavior when reference KB does not exist

Logged at WARNING level once per request (acceptable for v1; observability layer can dedupe later if log volume becomes an issue). The reference KB id is dropped from scope and the request proceeds with `[primary]`. No 4xx/5xx is returned to the client — the analyst gets degraded but correct behavior for the primary KB.

This matches the failure-tolerance pattern from the prior schema-index work (`_ensure_schema` logs and continues on per-statement DDL failure).

### 9. Testing

**Resolver unit tests** (`backend/tests/shared/test_kb_scope.py` — new file):
- Returns `[primary]` when domain config has no reference KB.
- Returns `[primary]` when primary IS the reference KB.
- Returns `[primary]` and logs WARNING when reference KB doesn't exist (use `caplog`).
- Returns `[primary, reference]` in that order when both exist.

**Graph adapter tests** (`backend/tests/graph/`):
- `get_entity` with a multi-KB scope returns the entity from whichever KB contains it.
- `search_entities` across two KBs returns the union of matches.
- Both in-memory and Neo4j (the Neo4j cases under `@pytest.mark.integration`).
- Single-element list `[primary]` still works (no regression).

**Vector adapter tests**:
- `VectorSearchRequest` with `knowledge_base_ids: [a, b]` returns matches from both KBs.
- Single-element scope behaves identically to old single-KB behavior.

**RAG service tests**:
- `answer_question(knowledge_base_ids=[primary, reference], ...)` retrieves context from both KBs.
- Backwards-compat: any existing tests that passed a scalar kb_id are updated to wrap it in `[...]`.

**Integration tests**:
- End-to-end: configure a domain with `default_reference_kb_id`, create two KBs, ingest data into each, hit an investigation endpoint, assert the response includes entities from both.

### 10. Files touched

| File / module | Change |
|---|---|
| `backend/config/schema.py` | Add `DomainConfig.default_reference_kb_id` field |
| `backend/shared/kb_scope.py` | New module with `resolve_kb_scope` |
| `backend/tests/shared/test_kb_scope.py` | New test file |
| `backend/graph/protocols.py` | Read-method signatures |
| `backend/graph/service.py` | Implementation matching new protocol |
| `backend/graph/adapters/in_memory.py` | `kb_id in kb_ids` filter |
| `backend/graph/adapters/neo4j_adapter.py` | `WHERE knowledge_base_id IN $knowledge_base_ids` |
| `backend/graph/adapters/protocols.py` | Repository-level read signatures |
| `backend/tests/graph/test_*.py` | Coverage for multi-KB and single-KB |
| `backend/vectorstore/protocols.py` | Documentation only (signatures unchanged) |
| `backend/vectorstore/service_models.py` | Search request/response field rename |
| `backend/vectorstore/service.py` | Use new field name |
| `backend/vectorstore/adapters/*.py` | Multi-KB filter |
| `backend/tests/vectorstore/test_*.py` | Coverage |
| `backend/rag/protocols.py` | `answer_question` signature |
| `backend/rag/service_models.py` | Query request/response field rename |
| `backend/rag/service.py` | Use new fields |
| `backend/tests/rag/test_*.py` | Coverage |
| `backend/api/routers/investigation.py` and other read routes | Call `resolve_kb_scope`; pass list |
| `backend/api/routers/rag.py` | Same |
| `backend/tests/api/*.py` | Coverage for handler-level scope expansion |
| `backend/graph/README.md` | Brief note that reads span scopes |
| `docs/architecture.md` | One-paragraph dual-graph addition |

## Success Criteria

- A domain config with `default_reference_kb_id: null` (or absent) produces identical behavior to today: reads scope to `[primary]`, no warnings logged, no regressions in any existing test.
- Setting `default_reference_kb_id: "<existing-kb-id>"` causes every read (entity lookup, entity search, RAG retrieval, vector search) to span both KBs.
- Setting `default_reference_kb_id: "<missing-kb-id>"` logs a WARNING per request and degrades to primary-only scope without 4xx/5xx.
- Writes are unaffected. `update_entity_properties`, `delete_knowledge_base`, `upsert_task`, `VectorIndexRequest`, and all KB-management endpoints behave identically to today.
- `query_neighborhood` continues to traverse a single KB; cross-KB joining is a deliberate non-feature for v1.
- `pyright --strict` clean, `ruff` clean, `pytest --cov` ≥ 85% in every package touched.
- `architecture.md` and `backend/graph/README.md` reflect the new contract.
