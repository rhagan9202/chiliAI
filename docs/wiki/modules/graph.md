# Module: graph

**Verified against codebase:** 2026-06-16
**Source:** `backend/graph/`

## Purpose

Graph database access abstraction. Owns graph CRUD (upsert entities/relationships), neighborhood queries, entity search, metrics computation, and knowledge-base-scoped deletion. Used by both the worker (upsert pipeline) and the API (entity detail, KB status).

---

## Service Protocol (`graph/protocols.py`)

```python
class GraphServiceProtocol(Protocol):
    def upsert_task(self, task: GraphBuildTask) -> GraphBuildReceipt: ...
    def get_entity(self, knowledge_base_ids: list[str], entity_id: str) -> Entity | None: ...
    def update_entity_properties(
        self,
        knowledge_base_id: str,
        entity_id: str,
        properties: dict[str, object],
    ) -> Entity: ...
    def query_neighborhood(
        self,
        knowledge_base_id: str,
        entity_id: str,
        depth: int,
    ) -> SubgraphResult: ...
    def get_subgraph(
        self,
        knowledge_base_id: str,
        seed_entity_ids: list[str],
        depth: int = 1,
    ) -> SubgraphResult: ...
    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]: ...
    def compute_metrics(self, knowledge_base_id: str) -> GraphMetrics: ...
    def delete_knowledge_base(self, knowledge_base_id: str) -> None: ...
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance: ...
```

---

## Service Models (`graph/service_models.py`)

Last verified: 2026-05-20

```python
class GraphBuildTask(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    validation_storage_key: str          # non-empty; enforced by model_validator
    correlation_id: str                  # default_factory=generate_id
    entities: list[Entity] = []
    relationships: list[Relationship] = []

class GraphBuildReceipt(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    extraction_result_id: str
    validation_report_id: str
    validation_storage_key: str
    graph_update_storage_key: str
    upserted_entity_count: int           # >= 0
    upserted_relationship_count: int     # >= 0
    created_at: datetime                 # default_factory=utc_now

class NeighborhoodRequest(BaseModel):
    """API-facing request for investigation neighborhood queries."""
    knowledge_base_id: str
    entity_id: str
    depth: int = Field(default=2, ge=1, le=5)

class EntityDetailResponse(BaseModel):
    entity: Entity

class NeighborhoodResponse(BaseModel):
    center_entity_id: str
    entities: list[Entity] = []
    relationships: list[Relationship] = []

class EntitySearchResponse(BaseModel):
    items: list[Entity] = []
    total: int                           # >= 0

class GraphMetricsResult(BaseModel):
    knowledge_base_id: str
    metrics: GraphMetrics
    created_at: datetime
```

Also used internally: `EntitySearchQuery`, `NeighborhoodQuery` (worker-level query params).

---

## Models (`graph/models.py`)

Last verified: 2026-05-22

```python
class GraphUpsertResult(BaseModel):
    knowledge_base_id: str
    source_document_id: str
    parsed_document_id: str
    validation_report_id: str
    extraction_result_id: str
    upserted_entity_ids: list[str] = []
    upserted_relationship_ids: list[str] = []
    created_at: datetime

class SubgraphResult(BaseModel):
    entities: list[Entity] = []
    relationships: list[Relationship] = []

class GraphMetrics(BaseModel):
    entity_count: int          # >= 0
    relationship_count: int    # >= 0
    avg_degree: float          # >= 0.0

class GraphDeleteByProvenance(BaseModel):
    """Counts returned from a provenance-scoped delete."""
    knowledge_base_id: str
    source_document_id: str
    entity_count: int          # >= 0
    relationship_count: int    # >= 0
```

`GraphDeleteByProvenance` is returned by `delete_by_source_document`. The Neo4j adapter uses `CONTAINS` on serialized `metadata_json` for the cascade-delete query; a migration to a dedicated indexed column is noted in the code as a production path.

---

## Adapters

| Backend | File | Config |
|---------|------|--------|
| In-memory | `adapters/in_memory.py` | `GraphDbConfig.backend = "in_memory"` |
| Neo4j | `adapters/neo4j_adapter.py` | `backend = "neo4j"`, `uri`, `auth_env_var` |

Inner adapter protocol: `adapters/protocols.py` (structural subset consumed by the service). It includes `get_subgraph(knowledge_base_id, seed_entity_ids, depth=1)` for a single-KB deduplicated union of seed neighborhoods.

Neo4j adapter uses lazy import via `importlib` to avoid hard dependency without `[neo4j]` extra.

---

## Module Dependencies

- `shared/types.py` — `Entity`, `Relationship`
- `config/schema.py` — `GraphDbConfig`
- Optional: `neo4j` driver (skipped without `[neo4j]` extra)

---

## Tests

Location: `backend/tests/graph/`
Neo4j adapter tests marked `@pytest.mark.integration`.
