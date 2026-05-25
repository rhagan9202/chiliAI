# Ingestion Pipeline E2E Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the chiliAI ingestion pipeline to a demo-quality E2E state for the medicare_fraud domain: KB creation → real NPPES (TN-filtered) + DE-SynPUF (TN-cross-filtered) records → LLM-extracted document policies (Ollama fallback) → populated graph + RAG-searchable vector index, with idempotent re-upload and cascading KB delete.

**Architecture:** Thin vertical slice first (Approach A from spec). Records flow exercises the seams (graph + vector + delete cascade) in Increment 1. Lifecycle hardening in Increment 2. Then configuration (NPPES/DE-SynPUF YAML), subset tooling, LLM extraction adapter chain, the extractor itself, and finally E2E + docs.

**Tech Stack:** Python 3.12 / FastAPI / pytest / pyright --strict, React 19 / Vite 8 / TypeScript strict, Neo4j 5, Qdrant, Redis Streams, MinIO/local FS object store, Ollama (HTTP API via httpx), CMS DE-SynPUF + NPPES CSVs.

**Reference spec:** `docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`

---

## Conventions Used in This Plan

- All file paths are absolute from the repo root unless noted otherwise.
- Run pytest from the `backend/` directory unless a path is given. Activate the host venv if you are not in Docker: `source backend/.venv/bin/activate` (see CLAUDE.md `dev_environment.md` memory note).
- For pyright runs use `cd backend && pyright`. The strict-mode include list lives in `backend/pyproject.toml`; if you add a new module that should be strict-checked, also add it to `tool.pyright.include`.
- Every task ends with a commit. Commit subject style follows the repo's existing convention: `type(scope): short summary`. Examples in `git log`.
- TDD discipline: write the failing test FIRST, verify it fails for the right reason (not import error), then implement, then verify it passes. Each test step must be runnable in isolation.
- Do not bypass `--strict` or coverage gates. If pyright complains about a new module, fix the annotations rather than excluding the module. Coverage gate is ≥85% per package.

---

## Phase 1 — Thin Vertical Slice (records → graph → vector → delete)

This phase wires the records pipeline through the embed-and-index step and proves the cascade-delete primitives end to end. No LLM or new data work here — purely structural plumbing using existing CMS feed fixtures.

### Task 1.1: Add `metadata` field to `Relationship`

**Files:**
- Modify: `backend/shared/types.py:90-102`
- Test: `backend/tests/shared/test_types_relationship_metadata.py` (new)

**Why:** `Entity` already carries a `metadata: dict[str, Any]` slot we can use for provenance. `Relationship` does not. Adding it is the smallest possible contract change to support per-source provenance for both record-sourced and document-sourced relationships.

- [ ] **Step 1: Write failing test**

Create `backend/tests/shared/test_types_relationship_metadata.py`:

```python
"""Verify Relationship carries an opaque metadata dict for provenance."""

from __future__ import annotations

from shared.types import Relationship


def test_relationship_has_default_empty_metadata() -> None:
    relationship = Relationship(
        id="rel-1",
        type="submitted_by",
        source_id="claim:A",
        target_id="provider:B",
    )
    assert relationship.metadata == {}


def test_relationship_accepts_metadata() -> None:
    relationship = Relationship(
        id="rel-1",
        type="submitted_by",
        source_id="claim:A",
        target_id="provider:B",
        metadata={"source_kind": "record", "source_feed": "carrier_claims_a"},
    )
    assert relationship.metadata["source_kind"] == "record"
    assert relationship.metadata["source_feed"] == "carrier_claims_a"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/shared/test_types_relationship_metadata.py -v
```

Expected: FAIL — `TypeError: Relationship() got unexpected keyword argument 'metadata'` on the second test, first test passes vacuously.

- [ ] **Step 3: Add the field**

In `backend/shared/types.py` around line 102, modify the `Relationship` class:

```python
class Relationship(BaseModel):
    """A relationship whose ``type`` matches a ``RelationshipDefinition.name``."""

    id: str
    type: str
    source_id: str
    target_id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime | None = None
    version: int = 1
    weight: float | None = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/shared/test_types_relationship_metadata.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Run pyright**

```bash
cd backend && pyright shared/types.py tests/shared/test_types_relationship_metadata.py
```

Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/shared/types.py backend/tests/shared/test_types_relationship_metadata.py
git commit -m "feat(shared): add Relationship.metadata field for provenance"
```

---

### Task 1.2: Stamp records-pipeline provenance on entities and relationships

**Files:**
- Modify: `backend/records/mappers/feed_mapper.py:49-95`
- Test: `backend/tests/records/test_feed_mapper_provenance.py` (new)

**Why:** Cascade delete by source (Increment 2) needs to know which writes came from which feed/record. Stamping provenance into entity/relationship metadata at mapping time is the only point where the records pipeline has both pieces of information.

- [ ] **Step 1: Write failing test**

Create `backend/tests/records/test_feed_mapper_provenance.py`:

```python
"""Records-mapped entities and relationships carry source provenance."""

from __future__ import annotations

from datetime import datetime, timezone

from config.schema import (
    RecordEntityMapping,
    RecordFeedConfig,
    RecordRelationshipMapping,
)
from records.mappers.feed_mapper import map_batch
from records.models import RawRecord
from shared.types import PropertyDefinition, PropertyType


def _record(payload: dict[str, object], record_id: str = "r1") -> RawRecord:
    return RawRecord(
        record_id=record_id,
        knowledge_base_id="kb-1",
        feed_name="carrier_claims_a",
        record_type="carrier_claim_record",
        content_hash="hash-" + record_id,
        payload=payload,
        ingested_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _feed() -> RecordFeedConfig:
    return RecordFeedConfig(
        name="carrier_claims_a",
        record_type="carrier_claim_record",
        source="file_upload",
        id_field="CLM_ID",
        record_schema={
            "CLM_ID": PropertyDefinition(type=PropertyType.STRING, display="Claim ID", required=True),
            "NPI": PropertyDefinition(type=PropertyType.STRING, display="NPI"),
        },
        entities=[
            RecordEntityMapping(
                entity_type="claim",
                id_field="CLM_ID",
                property_fields={"claim_id": "CLM_ID"},
            ),
            RecordEntityMapping(
                entity_type="provider",
                id_field="NPI",
                property_fields={"npi": "NPI"},
            ),
        ],
        relationships=[
            RecordRelationshipMapping(
                relationship_type="submitted_by",
                source_entity_type="claim",
                target_entity_type="provider",
            ),
        ],
    )


def test_entity_carries_source_provenance() -> None:
    result = map_batch(_feed(), [_record({"CLM_ID": "C1", "NPI": "1234567890"})])

    claim = next(e for e in result.entities if e.type == "claim")
    assert claim.metadata["source_kind"] == "record"
    assert claim.metadata["source_feed"] == "carrier_claims_a"
    assert claim.metadata["source_raw_record_id"] == "r1"


def test_relationship_carries_source_provenance() -> None:
    result = map_batch(_feed(), [_record({"CLM_ID": "C1", "NPI": "1234567890"})])

    rel = result.relationships[0]
    assert rel.metadata["source_kind"] == "record"
    assert rel.metadata["source_feed"] == "carrier_claims_a"
    assert rel.metadata["source_raw_record_id"] == "r1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/records/test_feed_mapper_provenance.py -v
```

Expected: FAIL — `KeyError: 'source_kind'`.

- [ ] **Step 3: Implement provenance stamping**

Edit `backend/records/mappers/feed_mapper.py`. In `map_batch`, when constructing entities and relationships, add metadata. Replace the entity construction inside the `for record in records:` loop and the relationship construction:

```python
            entities[entity_id] = Entity(
                id=entity_id,
                type=entity_mapping.entity_type,
                properties=properties,
                metadata={
                    "source_kind": "record",
                    "source_feed": feed.name,
                    "source_raw_record_id": record.record_id,
                },
            )
```

```python
            relationships[relationship_id] = Relationship(
                id=relationship_id,
                type=relationship_mapping.relationship_type,
                source_id=source_id,
                target_id=target_id,
                metadata={
                    "source_kind": "record",
                    "source_feed": feed.name,
                    "source_raw_record_id": record.record_id,
                },
            )
```

Note: when multiple records collapse to the same `entity_id`, the dict overwrite means the last record's provenance wins. That is acceptable for the demo — the dedupe path picks one canonical source. A follow-up could aggregate `source_raw_record_ids: list[str]` but it is not needed for the cascade-delete-by-document path (records cleanup is per-feed, not per-record).

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/records/test_feed_mapper_provenance.py -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Run full records test package + pyright**

```bash
cd backend && pytest tests/records -v && pyright records
```

Expected: 0 failures, 0 pyright errors. Existing tests must still pass — provenance is additive.

- [ ] **Step 6: Commit**

```bash
git add backend/records/mappers/feed_mapper.py backend/tests/records/test_feed_mapper_provenance.py
git commit -m "feat(records): stamp source provenance on mapped entities and relationships"
```

---

### Task 1.3: Stamp documents-pipeline provenance on candidate entities and relationships

**Files:**
- Modify: `backend/ingestion/extractor.py:124-139` (entity construction) and `:166-182` (relationship construction)
- Test: `backend/tests/ingestion/test_extractor_provenance.py` (new)

**Why:** Mirror the records-side provenance so the document pipeline can be cleaned up by `(source_kind="document", source_document_id=...)`. `PatternDocumentExtractor` already knows the source_document_id and chunk_id; we just lift them into the candidate's metadata.

The intermediate models `CandidateEntity` and `CandidateRelationship` (in `backend/ingestion/models.py`) already carry `source_document_id` and `chunk_id` as first-class fields, but those are intermediate, not Entity/Relationship. The conversion from candidate → Entity happens in `backend/ingestion/validator.py` or similar. To keep this task scoped, write provenance at the point where the validator constructs the final `Entity`/`Relationship` for graph upsert.

- [ ] **Step 1: Locate the candidate-to-entity conversion**

```bash
cd backend && grep -rn "CandidateEntity\b" ingestion --include="*.py" | grep -v test
```

Identify the file that converts `CandidateEntity` → `Entity`. Likely candidates: `ingestion/validator.py`, `ingestion/service.py`, `agent/coordinator.py`. The conversion is the point that needs the metadata stamp.

- [ ] **Step 2: Write failing test against the conversion site**

Create `backend/tests/ingestion/test_extractor_provenance.py`. The exact test depends on the conversion site found in Step 1; use this template and adapt the import:

```python
"""Document-derived entities and relationships carry source provenance."""

from __future__ import annotations

# Adjust import to the actual conversion-site module identified in Step 1.
from ingestion.validator import build_entity_from_candidate  # type: ignore[attr-defined]
from ingestion.models import CandidateEntity, ExtractionEvidence


def _candidate() -> CandidateEntity:
    return CandidateEntity(
        id="cand-1",
        source_document_id="doc-1",
        chunk_id="chunk-7",
        type="provider",
        properties={"npi": "1234567890"},
        confidence=0.9,
        extraction_method="pattern_v1",
        evidence=[],
        metadata={},
    )


def test_built_entity_carries_document_provenance() -> None:
    entity = build_entity_from_candidate(_candidate())
    assert entity.metadata["source_kind"] == "document"
    assert entity.metadata["source_document_id"] == "doc-1"
    assert entity.metadata["source_chunk_id"] == "chunk-7"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && pytest tests/ingestion/test_extractor_provenance.py -v
```

Expected: FAIL — either `AttributeError` (function doesn't exist) or `KeyError: 'source_kind'`.

- [ ] **Step 4: Implement at the conversion site**

At the conversion site identified in Step 1, when constructing the `Entity` from a `CandidateEntity`, populate `metadata` from the candidate's source fields:

```python
def build_entity_from_candidate(candidate: CandidateEntity) -> Entity:
    return Entity(
        id=candidate.id,
        type=candidate.type,
        properties=candidate.properties,
        metadata={
            "source_kind": "document",
            "source_document_id": candidate.source_document_id,
            "source_chunk_id": candidate.chunk_id,
            **candidate.metadata,
        },
    )
```

Apply the same pattern to the `CandidateRelationship` → `Relationship` conversion. If a helper function does not already exist, add it next to the existing inline conversion code and route the inline code through it.

- [ ] **Step 5: Run test to verify it passes; run full ingestion suite**

```bash
cd backend && pytest tests/ingestion -v && pyright ingestion
```

Expected: New test passes, all existing ingestion tests pass, pyright 0 errors.

- [ ] **Step 6: Commit**

```bash
git add backend/ingestion backend/tests/ingestion/test_extractor_provenance.py
git commit -m "feat(ingestion): stamp source provenance on document-derived entities and relationships"
```

---

### Task 1.4: Wire embed-and-index step into `handle_records_ingested`

**Files:**
- Modify: `backend/agent/coordinator.py` (locate `handle_records_ingested` around line 1635)
- Test: `backend/tests/agent/test_coordinator_records_embeds.py` (new)

**Why:** After `upsert_records_graph` writes entities/relationships to the graph, the demo needs corresponding vector points so the KB is RAG-searchable. Today the records flow stops at graph write. The simplest path is: for each entity emitted, build a short text representation (`f"{display_label} {prop_summary}"`), pass through the embedding service, then index via `VectorService.index`.

- [ ] **Step 1: Read the current handler**

```bash
cd backend && sed -n '1620,1720p' agent/coordinator.py
```

Note its dependency injection signature — the embedding service and vector service may not yet be in scope. The simplest approach is to add them to the handler's keyword arguments and update the dispatch site (around line 2261).

- [ ] **Step 2: Write failing test**

Create `backend/tests/agent/test_coordinator_records_embeds.py`:

```python
"""handle_records_ingested writes vector points for every entity it persists."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent.coordinator import handle_records_ingested
from events.types import RecordsIngestedEvent
from shared.types import Entity, Relationship
from vectorstore.service_models import VectorIndexReceipt


def test_handler_indexes_vectors_for_persisted_entities() -> None:
    # Arrange: stub records service returns 2 entities, 1 relationship.
    entities = [
        Entity(id="provider:1234567890", type="provider", properties={"npi": "1234567890"}),
        Entity(id="claim:C1", type="claim", properties={"claim_id": "C1"}),
    ]
    relationships = [
        Relationship(id="submitted_by:claim:C1->provider:1234567890",
                     type="submitted_by",
                     source_id="claim:C1",
                     target_id="provider:1234567890"),
    ]

    records_service = MagicMock()
    records_service.map_for_event.return_value = (entities, relationships)

    graph_service = MagicMock()
    graph_service.upsert_records_graph.return_value = (entities, relationships)

    embedding_service = MagicMock()
    embedding_service.embed_texts.return_value = [[0.0] * 8, [0.0] * 8]

    vector_service = MagicMock()
    vector_service.index.return_value = [
        VectorIndexReceipt(knowledge_base_id="kb-1", record_id="v1", content_id="provider:1234567890", dimension=8),
        VectorIndexReceipt(knowledge_base_id="kb-1", record_id="v2", content_id="claim:C1", dimension=8),
    ]

    event = RecordsIngestedEvent(knowledge_base_id="kb-1", feed_name="carrier_claims_a", record_count=1)

    # Act
    handle_records_ingested(
        event,
        records_service=records_service,
        graph_service=graph_service,
        embedding_service=embedding_service,
        vector_service=vector_service,
    )

    # Assert: vector_service.index was called once with one submission per entity.
    assert vector_service.index.call_count == 1
    request = vector_service.index.call_args.args[0]
    assert request.knowledge_base_id == "kb-1"
    assert {s.content_id for s in request.submissions} == {"provider:1234567890", "claim:C1"}
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && pytest tests/agent/test_coordinator_records_embeds.py -v
```

Expected: FAIL — `handle_records_ingested` does not accept `embedding_service`/`vector_service` kwargs or does not call `vector_service.index`.

- [ ] **Step 4: Extend the handler**

In `backend/agent/coordinator.py`, modify the `handle_records_ingested` function signature to accept `embedding_service` and `vector_service` parameters (keyword-only). After the existing call to `graph_service.upsert_records_graph(...)`, add:

```python
    if embedding_service is not None and vector_service is not None and stored_entities:
        texts = [_entity_embedding_text(entity) for entity in stored_entities]
        vectors = embedding_service.embed_texts(texts)
        submissions = [
            VectorSubmission(
                content_id=entity.id,
                content=text,
                embedding=vector,
                metadata={
                    "source_kind": entity.metadata.get("source_kind", "record"),
                    "source_id": entity.id,
                    "entity_type": entity.type,
                },
            )
            for entity, text, vector in zip(stored_entities, texts, vectors, strict=True)
        ]
        vector_service.index(
            VectorIndexRequest(
                knowledge_base_id=event.knowledge_base_id,
                submissions=submissions,
            )
        )
```

Add a small helper near the top of the module:

```python
def _entity_embedding_text(entity: Entity) -> str:
    """Compose a deterministic embedding text from an entity's type + properties."""

    parts = [entity.type]
    for key in sorted(entity.properties.keys()):
        parts.append(f"{key}={entity.properties[key]}")
    return " ".join(parts)
```

Add the necessary imports (`VectorSubmission`, `VectorIndexRequest` from `vectorstore.service_models`, `Entity` from `shared.types`).

Also update the dispatch site around line 2261 to pass `embedding_service` and `vector_service` from the coordinator's dependency wiring (they should already be available — search for how `handle_documents_uploaded` receives the embedding service for the pattern).

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && pytest tests/agent/test_coordinator_records_embeds.py -v
```

Expected: PASS.

- [ ] **Step 6: Run full coordinator test suite + pyright**

```bash
cd backend && pytest tests/agent -v && pyright agent
```

Expected: 0 failures, 0 pyright errors. If existing coordinator tests fail because they construct `handle_records_ingested` without the new kwargs, update them to pass `embedding_service=None, vector_service=None` (the handler must remain backward-compatible when those are absent).

- [ ] **Step 7: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator_records_embeds.py
git commit -m "feat(agent): embed-and-index records-ingested entities into vectorstore"
```

---

### Task 1.5: E2E smoke — records flow populates graph + vectors, KB delete cascades

**Files:**
- Modify: `backend/tests/e2e/test_full_pipeline.py` (existing)
- (Optional fixture) `backend/tests/e2e/fixtures/tiny_carrier_claims.csv`

**Why:** Lock in the slice as an integration test so regressions surface immediately. Uses a 3-row CSV fixture against the existing medicare_fraud config; no LLM required.

- [ ] **Step 1: Create the fixture**

Create `backend/tests/e2e/fixtures/tiny_carrier_claims.csv`:

```csv
DESYNPUF_ID,CLM_ID,CLM_FROM_DT,CLM_THRU_DT,PRF_PHYSN_NPI_1,LINE_NCH_PMT_AMT_1
B0001,C1,20100101,20100102,1234567890,100.00
B0002,C2,20100103,20100104,1234567890,250.00
B0001,C3,20100105,20100106,2345678901,75.50
```

- [ ] **Step 2: Add the E2E test**

Append to `backend/tests/e2e/test_full_pipeline.py`:

```python
def test_records_e2e_populates_graph_and_vectors_and_cascade_deletes(
    api_client,                # existing fixture in this file
    graph_service,             # existing fixture
    vector_service,            # existing fixture
    raw_record_store,          # existing fixture
) -> None:
    # 1. Create KB
    create_response = api_client.post("/knowledgebases", json={"name": "tn-e2e", "description": "slice test"})
    assert create_response.status_code == 201
    kb_id = create_response.json()["id"]

    # 2. Upload 3-row carrier-claims fixture
    fixture_path = Path(__file__).parent / "fixtures" / "tiny_carrier_claims.csv"
    with fixture_path.open("rb") as fh:
        upload = api_client.post(
            f"/records/{kb_id}/files",
            files={"file": ("tiny_carrier_claims.csv", fh, "text/csv")},
            data={"feed_name": "carrier_claims_a"},
        )
    assert upload.status_code == 202

    # 3. Drain worker (use existing helper in this file)
    drain_worker_events(timeout_seconds=30)

    # 4. Assert graph populated
    metrics = graph_service.compute_metrics(kb_id)
    # 3 claims, 2 distinct beneficiaries, 2 distinct providers = 7 entities; 6 relationships (3 billed_for + 3 submitted_by)
    assert metrics.entity_count == 7
    assert metrics.relationship_count == 6

    # 5. Assert vector index populated (one point per entity)
    assert vector_service.count(kb_id) == 7

    # 6. Assert raw_records persisted
    assert raw_record_store.count_for_kb(kb_id) == 3

    # 7. Cascade delete
    delete = api_client.delete(f"/knowledgebases/{kb_id}")
    assert delete.status_code == 204

    # 8. Assert clean state
    assert graph_service.compute_metrics(kb_id).entity_count == 0
    assert vector_service.count(kb_id) == 0
    # raw_records cascade is added in Phase 2 — for now this slice does not assert it.
```

If a fixture or helper referenced above does not exist in `test_full_pipeline.py`, read the top of that file for the existing fixture names and substitute the closest equivalents. If essential plumbing (`drain_worker_events`, `raw_record_store`) does not exist, add the simplest possible version of it directly to the test module.

- [ ] **Step 3: Run the test**

```bash
cd backend && pytest tests/e2e/test_full_pipeline.py::test_records_e2e_populates_graph_and_vectors_and_cascade_deletes -v
```

Expected: PASS. If it fails with infrastructure errors (Neo4j/Qdrant/Redis), start the dev stack first: `make dev` from the repo root, then re-run.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/e2e/test_full_pipeline.py backend/tests/e2e/fixtures/tiny_carrier_claims.csv
git commit -m "test(e2e): records flow populates graph+vectors and survives KB delete"
```

---

## Phase 2 — KB Lifecycle Hardening

Re-upload idempotency, KB delete cascade with 207 partial-failure semantics, advisory locks, workflow-busy guard.

### Task 2.1: Add `delete_by_source_document` to GraphRepository protocol + adapters

**Files:**
- Modify: `backend/graph/adapters/protocols.py`
- Modify: `backend/graph/adapters/in_memory.py`
- Modify: `backend/graph/adapters/neo4j_adapter.py`
- Test: `backend/tests/graph/test_delete_by_source_document.py` (new)

**Why:** Document re-upload needs to drop the old extraction's graph rows before reinserting the new. Provenance is stamped on entity/relationship metadata (Task 1.3), so the operation is "delete all entities and relationships where `metadata.source_document_id == document_id` for this KB."

- [ ] **Step 1: Read existing protocol surface**

```bash
cd backend && sed -n '1,60p' graph/adapters/protocols.py
```

Note the existing method shapes (transaction context manager, upsert_entities, etc.).

- [ ] **Step 2: Write failing test**

Create `backend/tests/graph/test_delete_by_source_document.py`:

```python
"""Graph repository removes entities/relationships keyed by source_document_id."""

from __future__ import annotations

from graph.adapters.in_memory import InMemoryGraphRepository
from shared.types import Entity, Relationship


def test_delete_by_source_document_removes_only_matching_provenance() -> None:
    repo = InMemoryGraphRepository()
    with repo.transaction("kb-1"):
        repo.upsert_entities("kb-1", [
            Entity(id="e1", type="provider", properties={"npi": "1"},
                   metadata={"source_kind": "document", "source_document_id": "doc-A"}),
            Entity(id="e2", type="provider", properties={"npi": "2"},
                   metadata={"source_kind": "document", "source_document_id": "doc-B"}),
            Entity(id="e3", type="provider", properties={"npi": "3"},
                   metadata={"source_kind": "record", "source_feed": "nppes_providers"}),
        ])
        repo.upsert_relationships("kb-1", [
            Relationship(id="r1", type="referred_by", source_id="e1", target_id="e2",
                         metadata={"source_kind": "document", "source_document_id": "doc-A"}),
        ])

    deleted = repo.delete_by_source_document("kb-1", "doc-A")
    assert deleted.entity_count == 1
    assert deleted.relationship_count == 1
    assert repo.count_entities("kb-1") == 2
    assert repo.count_relationships("kb-1") == 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && pytest tests/graph/test_delete_by_source_document.py -v
```

Expected: FAIL — `AttributeError: 'InMemoryGraphRepository' object has no attribute 'delete_by_source_document'`.

- [ ] **Step 4: Add to protocol**

In `backend/graph/adapters/protocols.py`, add to the `GraphRepository` Protocol:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance: ...
```

Add a small return model. Open `backend/graph/models.py` and add:

```python
class GraphDeleteByProvenance(BaseModel):
    """Counts returned from a provenance-scoped delete."""

    knowledge_base_id: str
    source_document_id: str
    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
```

Import it into `protocols.py`. Re-export in `__all__`.

- [ ] **Step 5: Implement in-memory**

In `backend/graph/adapters/in_memory.py`, add:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance:
        kb = self._kbs.get(knowledge_base_id)
        if kb is None:
            return GraphDeleteByProvenance(
                knowledge_base_id=knowledge_base_id,
                source_document_id=source_document_id,
                entity_count=0,
                relationship_count=0,
            )
        keep_entities: dict[str, Entity] = {}
        removed_entities = 0
        for entity_id, entity in kb.entities.items():
            if entity.metadata.get("source_document_id") == source_document_id:
                removed_entities += 1
                continue
            keep_entities[entity_id] = entity
        kb.entities = keep_entities

        keep_relationships: dict[str, Relationship] = {}
        removed_relationships = 0
        for rel_id, rel in kb.relationships.items():
            if rel.metadata.get("source_document_id") == source_document_id:
                removed_relationships += 1
                continue
            keep_relationships[rel_id] = rel
        kb.relationships = keep_relationships

        return GraphDeleteByProvenance(
            knowledge_base_id=knowledge_base_id,
            source_document_id=source_document_id,
            entity_count=removed_entities,
            relationship_count=removed_relationships,
        )
```

Adjust the attribute access (`self._kbs`, `kb.entities`, `kb.relationships`) to match the actual in-memory adapter's storage layout — read the existing file first to confirm names.

- [ ] **Step 6: Implement Neo4j**

In `backend/graph/adapters/neo4j_adapter.py`, add:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance:
        with self._driver.session() as session:
            relationship_result = session.run(
                """
                MATCH ()-[r {knowledge_base_id: $kb_id, source_document_id: $doc_id}]->()
                WITH r, count(r) AS deleted_count
                DELETE r
                RETURN deleted_count
                """,
                kb_id=knowledge_base_id, doc_id=source_document_id,
            )
            relationship_count = relationship_result.single()["deleted_count"] if relationship_result.peek() else 0

            entity_result = session.run(
                """
                MATCH (n {knowledge_base_id: $kb_id, source_document_id: $doc_id})
                WITH n, count(n) AS deleted_count
                DETACH DELETE n
                RETURN deleted_count
                """,
                kb_id=knowledge_base_id, doc_id=source_document_id,
            )
            entity_count = entity_result.single()["deleted_count"] if entity_result.peek() else 0

        return GraphDeleteByProvenance(
            knowledge_base_id=knowledge_base_id,
            source_document_id=source_document_id,
            entity_count=entity_count,
            relationship_count=relationship_count,
        )
```

Note: this assumes entities are written with `source_document_id` as a node property (which provenance metadata stamping should produce). Verify by reading how `upsert_entities` writes properties in the Neo4j adapter — if `metadata` is stored as nested JSON rather than flattened, change the Cypher to `(n {knowledge_base_id: $kb_id, metadata: {source_document_id: $doc_id}})` or unwind it during the upsert.

- [ ] **Step 7: Run tests + pyright**

```bash
cd backend && pytest tests/graph -v && pyright graph
```

Expected: New test passes, all existing graph tests pass, 0 pyright errors.

- [ ] **Step 8: Commit**

```bash
git add backend/graph
git commit -m "feat(graph): add delete_by_source_document for provenance-scoped cleanup"
```

---

### Task 2.2: Add `GraphService.delete_by_source_document` wrapper

**Files:**
- Modify: `backend/graph/service.py:300`
- Modify: `backend/graph/protocols.py`
- Test: `backend/tests/graph/test_service_delete_by_source_document.py` (new)

- [ ] **Step 1: Write failing test**

Create `backend/tests/graph/test_service_delete_by_source_document.py`:

```python
from __future__ import annotations

from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService
from shared.types import Entity
from events.adapters.in_memory import InMemoryEventBus
from storage.adapters.in_memory import InMemoryObjectStore


def test_service_delegates_to_repository() -> None:
    repo = InMemoryGraphRepository()
    service = GraphService(repo, object_store=InMemoryObjectStore(), event_bus=InMemoryEventBus())

    with repo.transaction("kb-1"):
        repo.upsert_entities("kb-1", [
            Entity(id="e1", type="provider", properties={"npi": "1"},
                   metadata={"source_kind": "document", "source_document_id": "doc-A"}),
        ])

    report = service.delete_by_source_document("kb-1", "doc-A")
    assert report.entity_count == 1
    assert repo.count_entities("kb-1") == 0
```

- [ ] **Step 2: Run + verify fails; implement**

In `backend/graph/protocols.py`, add to `GraphServiceProtocol`:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance: ...
```

In `backend/graph/service.py`, after `delete_knowledge_base`:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> GraphDeleteByProvenance:
        return self._repository.delete_by_source_document(knowledge_base_id, source_document_id)
```

Add the `GraphDeleteByProvenance` import.

- [ ] **Step 3: Run test, pyright, commit**

```bash
cd backend && pytest tests/graph/test_service_delete_by_source_document.py -v && pyright graph
git add backend/graph
git commit -m "feat(graph): expose delete_by_source_document on GraphService"
```

---

### Task 2.3: Add `VectorService.delete_by_source_document`

**Files:**
- Modify: `backend/vectorstore/service.py:198` (after `delete_knowledge_base`)
- Modify: `backend/vectorstore/adapters/protocols.py` and adapters
- Modify: `backend/vectorstore/service_models.py` (add response model if needed)
- Test: `backend/tests/vectorstore/test_delete_by_source_document.py` (new)

**Why:** Mirror the graph operation for vector points. Points are tagged with metadata that includes `source_kind` and `source_id` (Task 1.4 wires this), but for documents the metadata should also include `source_document_id` — verify by reading how `handle_documents_uploaded` constructs vector submissions.

- [ ] **Step 1: Verify document-side vector metadata carries source_document_id**

```bash
cd backend && grep -n "VectorSubmission" agent/coordinator.py | head -20
```

If document vector submissions do not yet include `source_document_id` in their metadata, add it to the submission construction in `handle_documents_uploaded`. Each vector point should carry `{"source_kind": "document", "source_id": chunk.id, "source_document_id": doc.id, "chunk_id": chunk.id}` in metadata.

- [ ] **Step 2: Write failing test**

Create `backend/tests/vectorstore/test_delete_by_source_document.py`:

```python
from __future__ import annotations

from events.adapters.in_memory import InMemoryEventBus
from vectorstore.adapters.in_memory import InMemoryVectorStore
from vectorstore.models import VectorRecord
from vectorstore.service import VectorService


def test_delete_by_source_document_removes_only_matching_points() -> None:
    store = InMemoryVectorStore(dimension=3)
    service = VectorService(store, event_bus=InMemoryEventBus())

    store.upsert_records("kb-1", [
        VectorRecord(id="v1", knowledge_base_id="kb-1", content_id="c1",
                     embedding=[1.0, 0.0, 0.0], content="a",
                     metadata={"source_kind": "document", "source_document_id": "doc-A"}),
        VectorRecord(id="v2", knowledge_base_id="kb-1", content_id="c2",
                     embedding=[0.0, 1.0, 0.0], content="b",
                     metadata={"source_kind": "document", "source_document_id": "doc-B"}),
        VectorRecord(id="v3", knowledge_base_id="kb-1", content_id="c3",
                     embedding=[0.0, 0.0, 1.0], content="c",
                     metadata={"source_kind": "record", "source_feed": "nppes_providers"}),
    ])

    response = service.delete_by_source_document("kb-1", "doc-A")
    assert response.deleted_count == 1
    assert store.count_records("kb-1") == 2
```

- [ ] **Step 3: Implement**

In `backend/vectorstore/adapters/protocols.py`, add to `VectorStoreProtocol`:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> int: ...
```

In `backend/vectorstore/adapters/in_memory.py`:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> int:
        namespace = self._records.get(knowledge_base_id, {})
        to_delete = [
            record_id
            for record_id, record in namespace.items()
            if record.metadata.get("source_document_id") == source_document_id
        ]
        for record_id in to_delete:
            namespace.pop(record_id, None)
        return len(to_delete)
```

(Adjust attribute names to match the actual in-memory store implementation.)

In `backend/vectorstore/adapters/qdrant_adapter.py`, implement via Qdrant payload-filtered delete using the existing client. Pattern: build a `Filter` over the `metadata.source_document_id == source_document_id` payload and call `client.delete(collection_name=..., points_selector=FilterSelector(filter=filter))`. Refer to the existing `delete_namespace` implementation for the client-call style and error wrapping.

In `backend/vectorstore/service.py`, after `delete_knowledge_base`:

```python
    def delete_by_source_document(
        self,
        knowledge_base_id: str,
        source_document_id: str,
    ) -> VectorDeleteResponse:
        try:
            deleted_count = self._store.delete_by_source_document(knowledge_base_id, source_document_id)
        except Exception as exc:
            raise VectorStoreError("Failed to delete vectors by source document.") from exc
        return VectorDeleteResponse(
            knowledge_base_id=knowledge_base_id,
            deleted_count=deleted_count,
        )
```

- [ ] **Step 4: Run tests, pyright, commit**

```bash
cd backend && pytest tests/vectorstore -v && pyright vectorstore
git add backend/vectorstore backend/tests/vectorstore/test_delete_by_source_document.py
git commit -m "feat(vectorstore): add delete_by_source_document for provenance-scoped cleanup"
```

---

### Task 2.4: Add workflow-busy check helper and `KbBusyError` exception

**Files:**
- Create: `backend/api/_kb_busy.py`
- Test: `backend/tests/api/test_kb_busy.py` (new)

**Why:** Re-upload, document delete, and KB delete all need to refuse to run while a workflow is mid-flight. Centralize the check.

- [ ] **Step 1: Write failing test**

Create `backend/tests/api/test_kb_busy.py`:

```python
from __future__ import annotations

import pytest

from api._kb_busy import KbBusyError, ensure_kb_idle


def test_idle_kb_does_not_raise() -> None:
    class StubTracker:
        def is_busy(self, kb_id: str) -> bool:
            return False

    ensure_kb_idle("kb-1", tracker=StubTracker())  # no exception


def test_busy_kb_raises() -> None:
    class StubTracker:
        def is_busy(self, kb_id: str) -> bool:
            return True

    with pytest.raises(KbBusyError):
        ensure_kb_idle("kb-1", tracker=StubTracker())
```

- [ ] **Step 2: Implement**

Create `backend/api/_kb_busy.py`:

```python
"""Helper for refusing mutations while a KB workflow is in flight."""

from __future__ import annotations

from typing import Protocol


class KbBusyError(Exception):
    """Raised when a KB-scoped mutation is attempted during an active workflow."""

    def __init__(self, knowledge_base_id: str) -> None:
        super().__init__(
            f"Knowledge base '{knowledge_base_id}' has a workflow in progress."
        )
        self.knowledge_base_id = knowledge_base_id


class WorkflowBusyTracker(Protocol):
    def is_busy(self, knowledge_base_id: str) -> bool: ...


def ensure_kb_idle(
    knowledge_base_id: str,
    *,
    tracker: WorkflowBusyTracker,
) -> None:
    if tracker.is_busy(knowledge_base_id):
        raise KbBusyError(knowledge_base_id)


__all__ = ["KbBusyError", "WorkflowBusyTracker", "ensure_kb_idle"]
```

- [ ] **Step 3: Wire the existing workflow tracker**

Find the existing workflow tracker (`backend/agent/workflow_tracking.py` per memory notes / explore output). Add or expose an `is_busy(kb_id) -> bool` method that returns True when there is a non-terminal workflow run for the KB. If the tracker already has this method, no change needed.

```bash
cd backend && grep -n "class.*Tracker\b" agent/workflow_tracking.py
```

- [ ] **Step 4: Run test, pyright, commit**

```bash
cd backend && pytest tests/api/test_kb_busy.py -v && pyright api/_kb_busy.py
git add backend/api/_kb_busy.py backend/tests/api/test_kb_busy.py
git commit -m "feat(api): add KbBusyError + ensure_kb_idle workflow-busy guard"
```

---

### Task 2.5: Cascade-delete the KB through graph + vector + raw_records + object store + repository

**Files:**
- Modify: `backend/api/routers/knowledgebases.py:161-188` (existing DELETE endpoint)
- Modify: `backend/api/dependencies.py` (add `get_vector_service`, `get_raw_record_store`, `get_workflow_tracker` if missing)
- Test: `backend/tests/api/test_kb_delete_cascade.py` (new)

**Why:** Current DELETE only touches object_store + graph + repository. Add vector and raw_records cascade. Return 207 Multi-Status on partial failure, mark KB with `pending_cleanup` flag.

- [ ] **Step 1: Write failing test**

Create `backend/tests/api/test_kb_delete_cascade.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient


def test_delete_kb_cascades_through_all_stores(api_client: TestClient, graph_service, vector_service, raw_record_store, kb_repository) -> None:
    # Arrange: create KB, upload tiny records fixture (reuse the Phase-1 helper)
    kb_id = create_tiny_kb_with_records(api_client)

    assert graph_service.compute_metrics(kb_id).entity_count > 0
    assert vector_service.count(kb_id) > 0
    assert raw_record_store.count_for_kb(kb_id) > 0

    # Act
    response = api_client.delete(f"/knowledgebases/{kb_id}")
    assert response.status_code == 204

    # Assert all stores clean
    assert graph_service.compute_metrics(kb_id).entity_count == 0
    assert vector_service.count(kb_id) == 0
    assert raw_record_store.count_for_kb(kb_id) == 0
    assert kb_repository.get(kb_id) is None


def test_delete_kb_returns_207_on_partial_failure(api_client, monkeypatch, vector_service) -> None:
    kb_id = create_tiny_kb_with_records(api_client)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated vectorstore outage")

    monkeypatch.setattr(vector_service, "delete_knowledge_base", boom)

    response = api_client.delete(f"/knowledgebases/{kb_id}")
    assert response.status_code == 207
    body = response.json()
    statuses = {step["step"]: step["status"] for step in body["steps"]}
    assert statuses["vector"] == "failed"
    # Graph step ran before vector — it should be marked succeeded.
    assert statuses["graph"] == "succeeded"
    # The KB metadata stays with a pending_cleanup marker.
    assert body["pending_cleanup"] is True


def test_delete_kb_returns_409_when_workflow_busy(api_client, workflow_tracker) -> None:
    kb_id = create_tiny_kb_with_records(api_client)
    workflow_tracker.mark_busy(kb_id)

    response = api_client.delete(f"/knowledgebases/{kb_id}")
    assert response.status_code == 409
```

`create_tiny_kb_with_records` should be a helper in the same file that posts the Phase-1 fixture and drains the worker. If `workflow_tracker` doesn't expose `mark_busy` for testing, add a small test-only helper.

- [ ] **Step 2: Rewrite the DELETE endpoint**

Replace the body of `delete_knowledge_base` in `backend/api/routers/knowledgebases.py`:

```python
@router.delete(
    "/{knowledge_base_id}",
    dependencies=[Depends(require_role("admin"))],
)
async def delete_knowledge_base(
    knowledge_base_id: str,
    repository: KnowledgeBaseRepository = Depends(get_knowledge_base_repository),
    graph_service: GraphServiceProtocol = Depends(get_graph_service),
    vector_service: VectorServiceProtocol = Depends(get_vector_service),
    raw_record_store: RawRecordStoreProtocol = Depends(get_raw_record_store),
    object_store: ObjectStore = Depends(get_object_store),
    workflow_tracker: WorkflowBusyTracker = Depends(get_workflow_tracker),
    event_bus: EventBus = Depends(get_event_bus),
) -> Response:
    """Cascade-delete a KB across graph, vector, raw_records, object store, and metadata."""
    if repository.get(knowledge_base_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Knowledge base '{knowledge_base_id}' not found.",
        )

    try:
        ensure_kb_idle(knowledge_base_id, tracker=workflow_tracker)
    except KbBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    steps: list[dict[str, object]] = []
    pending_cleanup = False

    def _run(step_name: str, fn: Callable[[], object]) -> None:
        nonlocal pending_cleanup
        try:
            fn()
            steps.append({"step": step_name, "status": "succeeded"})
        except Exception as exc:  # noqa: BLE001 — we surface every failure
            pending_cleanup = True
            steps.append({"step": step_name, "status": "failed", "error": str(exc)})

    _run("graph", lambda: graph_service.delete_knowledge_base(knowledge_base_id))
    _run("vector", lambda: vector_service.delete_knowledge_base(knowledge_base_id))
    _run("raw_records", lambda: raw_record_store.delete_by_kb(knowledge_base_id))
    _run("object_store", lambda: _delete_object_store_prefix(object_store, knowledge_base_id))

    if pending_cleanup:
        # Keep the KB row but mark it; the worker handler will retry.
        repository.mark_pending_cleanup(knowledge_base_id)
        event_bus.publish(
            KnowledgeBaseDeletedEvent(
                knowledge_base_id=knowledge_base_id,
                cleanup_pending=True,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_207_MULTI_STATUS,
            content={
                "knowledge_base_id": knowledge_base_id,
                "pending_cleanup": True,
                "steps": steps,
            },
        )

    repository.delete(knowledge_base_id)
    event_bus.publish(
        KnowledgeBaseDeletedEvent(
            knowledge_base_id=knowledge_base_id,
            cleanup_pending=False,
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _delete_object_store_prefix(object_store: ObjectStore, knowledge_base_id: str) -> None:
    prefix = f"knowledgebases/{knowledge_base_id}/"
    for key in object_store.list_keys(prefix):
        object_store.delete(key)
```

Add imports:

```python
from typing import Callable

from fastapi import Response
from fastapi.responses import JSONResponse

from api._kb_busy import KbBusyError, WorkflowBusyTracker, ensure_kb_idle
from api.dependencies import get_raw_record_store, get_vector_service, get_workflow_tracker
from records.protocols import RawRecordStoreProtocol
from vectorstore.protocols import VectorServiceProtocol
```

Add `cleanup_pending: bool = False` to `KnowledgeBaseDeletedEvent` in `backend/events/types.py` if it does not already exist.

Add `mark_pending_cleanup(kb_id)` to `KnowledgeBaseRepository` in `backend/api/_kb_store.py`.

Add the missing dependency providers in `backend/api/dependencies.py`:

```python
def get_vector_service(...) -> VectorServiceProtocol: ...
def get_raw_record_store(...) -> RawRecordStoreProtocol: ...
def get_workflow_tracker(...) -> WorkflowBusyTracker: ...
```

(Use the existing pattern in `dependencies.py` — read `get_graph_service` for the template.)

- [ ] **Step 3: Run tests + pyright**

```bash
cd backend && pytest tests/api/test_kb_delete_cascade.py -v && pyright api
```

Expected: all three tests pass, pyright 0 errors. If existing tests against the old delete endpoint fail, update them to match the new behavior (204 on full success unchanged; 207 + body is new).

- [ ] **Step 4: Commit**

```bash
git add backend/api backend/events backend/tests/api/test_kb_delete_cascade.py
git commit -m "feat(api): cascade KB delete through graph+vector+records+storage with 207 on partial failure"
```

---

### Task 2.6: Worker retries `pending_cleanup` markers via `handle_knowledge_base_deleted`

**Files:**
- Modify: `backend/agent/coordinator.py` (add handler + dispatch wiring)
- Test: `backend/tests/agent/test_handle_knowledge_base_deleted.py` (new)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from unittest.mock import MagicMock

from agent.coordinator import handle_knowledge_base_deleted
from events.types import KnowledgeBaseDeletedEvent


def test_handler_retries_only_on_pending_cleanup_flag() -> None:
    graph_service = MagicMock()
    vector_service = MagicMock()
    raw_record_store = MagicMock()
    repository = MagicMock()

    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=False)
    handle_knowledge_base_deleted(
        event,
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        kb_repository=repository,
    )
    graph_service.delete_knowledge_base.assert_not_called()


def test_handler_retries_cascade_when_pending() -> None:
    graph_service = MagicMock()
    vector_service = MagicMock()
    raw_record_store = MagicMock()
    repository = MagicMock()

    event = KnowledgeBaseDeletedEvent(knowledge_base_id="kb-1", cleanup_pending=True)
    handle_knowledge_base_deleted(
        event,
        graph_service=graph_service,
        vector_service=vector_service,
        raw_record_store=raw_record_store,
        kb_repository=repository,
    )
    graph_service.delete_knowledge_base.assert_called_once_with("kb-1")
    vector_service.delete_knowledge_base.assert_called_once_with("kb-1")
    raw_record_store.delete_by_kb.assert_called_once_with("kb-1")
    repository.delete.assert_called_once_with("kb-1")
```

- [ ] **Step 2: Implement**

In `backend/agent/coordinator.py`, add:

```python
def handle_knowledge_base_deleted(
    event: KnowledgeBaseDeletedEvent,
    *,
    graph_service: GraphServiceProtocol,
    vector_service: VectorServiceProtocol,
    raw_record_store: RawRecordStoreProtocol,
    kb_repository: KnowledgeBaseRepository,
) -> None:
    if not event.cleanup_pending:
        return
    # Best-effort retries — exceptions bubble to the coordinator's DLQ flow.
    graph_service.delete_knowledge_base(event.knowledge_base_id)
    vector_service.delete_knowledge_base(event.knowledge_base_id)
    raw_record_store.delete_by_kb(event.knowledge_base_id)
    kb_repository.delete(event.knowledge_base_id)
```

Wire into the `_dispatch_event` block where other handlers are wired (around line 2200). Add the necessary imports.

- [ ] **Step 3: Run tests, pyright, commit**

```bash
cd backend && pytest tests/agent/test_handle_knowledge_base_deleted.py -v && pyright agent
git add backend/agent/coordinator.py backend/tests/agent/test_handle_knowledge_base_deleted.py
git commit -m "feat(agent): retry pending KB cleanup on KnowledgeBaseDeletedEvent"
```

---

### Task 2.7: Document re-upload idempotency

**Files:**
- Modify: `backend/api/routers/knowledgebases.py:275-348` (POST /documents)
- Modify: `backend/api/_kb_store.py` (add `get_document_by_content_hash`)
- Test: `backend/tests/api/test_document_reupload.py` (new)

**Why:** Posting the same `(filename, content_hash)` to a KB should drop the old extraction and reinsert. Surfaces `replaced_document_id` in the response.

- [ ] **Step 1: Compute content hash + store it on DocumentRecord**

Find `DocumentRecord` in `backend/api/_kb_store.py`. Add `content_hash: str | None = None` if absent. Compute the hash in the POST handler using `hashlib.sha256` over the bytes read from each upload.

- [ ] **Step 2: Add repository lookup**

In `backend/api/_kb_store.py`, add:

```python
    def get_document_by_content_hash(
        self,
        knowledge_base_id: str,
        content_hash: str,
    ) -> DocumentRecord | None:
        for record in self._documents_by_kb.get(knowledge_base_id, {}).values():
            if record.content_hash == content_hash:
                return record
        return None
```

(Adjust attribute names to the actual store.)

- [ ] **Step 3: Write failing test**

Create `backend/tests/api/test_document_reupload.py`:

```python
from __future__ import annotations

from io import BytesIO

import pytest


def test_reuploading_same_document_replaces_extraction(api_client, graph_service) -> None:
    create = api_client.post("/knowledgebases", json={"name": "reupload", "description": ""})
    kb_id = create.json()["id"]

    content = b"{\n  \"npi\": \"1234567890\",\n  \"specialty\": \"Cardiology\"\n}\n"
    first = api_client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("provider.json", BytesIO(content), "application/json"))],
    )
    assert first.status_code == 202
    original_doc_id = first.json()["documents"][0]["source_document_id"]

    second = api_client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("provider.json", BytesIO(content), "application/json"))],
    )
    assert second.status_code == 202
    body = second.json()["documents"][0]
    assert body.get("replaced_document_id") == original_doc_id
    # Same content hash → graph entity count should be stable, not doubled.
    # (assuming the regex extractor produces 1 entity from this content)
    assert graph_service.compute_metrics(kb_id).entity_count == 1
```

- [ ] **Step 4: Implement re-upload behavior**

In the POST handler, before calling `ingestion_service.register_documents`, for each upload:

```python
content_hash = hashlib.sha256(content).hexdigest()
existing = repository.get_document_by_content_hash(knowledge_base_id, content_hash)
replaced_document_id: str | None = None
if existing is not None:
    graph_service.delete_by_source_document(knowledge_base_id, existing.id)
    vector_service.delete_by_source_document(knowledge_base_id, existing.id)
    repository.delete_document(knowledge_base_id, existing.id)
    replaced_document_id = existing.id
```

Extend `DocumentReceipt` (or the response model) to include `replaced_document_id: str | None`.

Inject `graph_service` and `vector_service` into the POST handler via `Depends(...)`.

Pass `content_hash` to the `DocumentRecord` when calling `repository.add_document`.

- [ ] **Step 5: Run test, pyright, commit**

```bash
cd backend && pytest tests/api/test_document_reupload.py -v && pyright api
git add backend/api backend/tests/api/test_document_reupload.py
git commit -m "feat(api): document re-upload replaces old extraction via content-hash dedup"
```

---

### Task 2.8: Block uploads/deletes when KB is busy

**Files:**
- Modify: `backend/api/routers/knowledgebases.py` (POST /documents, DELETE /documents/{id})
- Modify: `backend/api/routers/records.py` (POST /records/{kb_id}/files) — find with `grep -rn "POST.*records" backend/api/routers/`
- Test: `backend/tests/api/test_workflow_busy_guard.py` (new)

**Why:** Same protection as KB delete. Mutating a KB mid-pipeline corrupts state.

- [ ] **Step 1: Write failing test**

```python
def test_document_upload_returns_409_when_busy(api_client, workflow_tracker) -> None:
    create = api_client.post("/knowledgebases", json={"name": "busy", "description": ""})
    kb_id = create.json()["id"]
    workflow_tracker.mark_busy(kb_id)

    response = api_client.post(
        f"/knowledgebases/{kb_id}/documents",
        files=[("files", ("a.json", b"{}", "application/json"))],
    )
    assert response.status_code == 409


def test_records_upload_returns_409_when_busy(api_client, workflow_tracker) -> None:
    # ... same pattern for /records/{kb_id}/files
    ...
```

- [ ] **Step 2: Implement**

In each handler, inject the workflow tracker and call `ensure_kb_idle` immediately after the existing KB existence check, converting `KbBusyError` to 409 the same way Task 2.5 does.

- [ ] **Step 3: Run tests, pyright, commit**

```bash
cd backend && pytest tests/api/test_workflow_busy_guard.py -v && pyright api
git add backend/api backend/tests/api/test_workflow_busy_guard.py
git commit -m "feat(api): block document/records uploads when KB workflow is busy"
```

---

## Phase 3 — NPPES + DE-SynPUF Configuration (Records Feeds)

Per-feed Python mappers are NOT needed — `records/mappers/feed_mapper.py` already generically applies `RecordFeedConfig`. This phase is purely YAML + entity-definition tweaks to declare the missing feeds and entity properties.

### Task 3.1: Add NPPES provider feed to medicare_fraud_cms_desynpuf.yaml

**Files:**
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`
- Test: `backend/tests/config/test_nppes_feed_loads.py` (new)

- [ ] **Step 1: Extend `provider` entity definition with NPPES properties**

In the existing yaml, replace the `provider` entity block (currently only `npi`) with:

```yaml
  - name: provider
    display_label: "Provider"
    icon: stethoscope
    properties:
      npi: { type: string, display: "NPI", required: true }
      entity_type_code: { type: string, display: "Entity Type Code" }       # 1=individual, 2=org
      organization_name: { type: string, display: "Organization Name" }
      last_name: { type: string, display: "Last Name" }
      first_name: { type: string, display: "First Name" }
      primary_taxonomy_code: { type: string, display: "Primary Taxonomy" }
      practice_state: { type: string, display: "Practice State" }
      practice_city: { type: string, display: "Practice City" }
      practice_postal_code: { type: string, display: "Practice Postal Code" }
      enumeration_date: { type: date, display: "Enumeration Date" }
      deactivation_date: { type: date, display: "Deactivation Date" }
```

- [ ] **Step 2: Add the NPPES feed**

Append under `records.feeds:`:

```yaml
    # ------------------------------------------------------------------
    # NPPES NPI Registry — one row per provider.
    # Source: tools/sample_data/build_tennessee_subset.py output
    # (nppes_providers_tn.csv).
    # ------------------------------------------------------------------
    - name: nppes_providers
      record_type: provider_record
      source: file_upload
      id_field: NPI
      allow_extra_fields: true
      record_schema:
        NPI: { type: string, display: "NPI", required: true }
        Entity Type Code: { type: string, display: "Entity Type Code" }
        Provider Organization Name (Legal Business Name): { type: string, display: "Organization Name" }
        Provider Last Name (Legal Name): { type: string, display: "Last Name" }
        Provider First Name: { type: string, display: "First Name" }
        Healthcare Provider Taxonomy Code_1: { type: string, display: "Primary Taxonomy" }
        Provider Business Practice Location Address State Name: { type: string, display: "Practice State" }
        Provider Business Practice Location Address City Name: { type: string, display: "Practice City" }
        Provider Business Practice Location Address Postal Code: { type: string, display: "Practice Postal Code" }
        Provider Enumeration Date: { type: date, display: "Enumeration Date" }
        NPI Deactivation Date: { type: date, display: "Deactivation Date" }
      entities:
        - entity_type: provider
          id_field: NPI
          property_fields:
            npi: NPI
            entity_type_code: "Entity Type Code"
            organization_name: "Provider Organization Name (Legal Business Name)"
            last_name: "Provider Last Name (Legal Name)"
            first_name: "Provider First Name"
            primary_taxonomy_code: "Healthcare Provider Taxonomy Code_1"
            practice_state: "Provider Business Practice Location Address State Name"
            practice_city: "Provider Business Practice Location Address City Name"
            practice_postal_code: "Provider Business Practice Location Address Postal Code"
            enumeration_date: "Provider Enumeration Date"
            deactivation_date: "NPI Deactivation Date"
```

NPPES column headers contain spaces, parens, and underscores — keep them verbatim per the NPPES spec.

- [ ] **Step 3: Write a test that loads the config and asserts the feed exists**

Create `backend/tests/config/test_nppes_feed_loads.py`:

```python
from __future__ import annotations

from pathlib import Path

from config.loader import load_domain_config


def test_nppes_feed_is_declared_in_medicare_fraud_cms_desynpuf() -> None:
    config_path = Path(__file__).parents[2] / "config" / "defaults" / "medicare_fraud_cms_desynpuf.yaml"
    config = load_domain_config(config_path)

    feed_names = {feed.name for feed in (config.records.feeds if config.records else [])}
    assert "nppes_providers" in feed_names

    provider = next(e for e in config.entities if e.name == "provider")
    assert "primary_taxonomy_code" in provider.properties
    assert "practice_state" in provider.properties
```

- [ ] **Step 4: Run test, pyright, commit**

```bash
cd backend && pytest tests/config/test_nppes_feed_loads.py -v && pyright config
git add backend/config/defaults/medicare_fraud_cms_desynpuf.yaml backend/tests/config/test_nppes_feed_loads.py
git commit -m "feat(config): declare NPPES provider feed + extended provider properties"
```

---

### Task 3.2: Add DE-SynPUF inpatient + outpatient claim feeds

**Files:**
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`
- Test: `backend/tests/config/test_desynpuf_claim_feeds_load.py` (new)

- [ ] **Step 1: Add inpatient feed**

Append:

```yaml
    # ------------------------------------------------------------------
    # Inpatient Claims — one row per inpatient stay.
    # Unique id: CLM_ID.
    # ------------------------------------------------------------------
    - name: inpatient_claims
      record_type: inpatient_claim_record
      source: file_upload
      id_field: CLM_ID
      allow_extra_fields: true
      record_schema:
        DESYNPUF_ID: { type: string, display: "Beneficiary ID", required: true }
        CLM_ID: { type: string, display: "Claim ID", required: true }
        CLM_FROM_DT: { type: date, display: "Claim From Date" }
        CLM_THRU_DT: { type: date, display: "Claim Through Date" }
        PRVDR_NUM: { type: string, display: "Provider Number" }
        AT_PHYSN_NPI: { type: string, display: "Attending Physician NPI" }
        CLM_PMT_AMT: { type: decimal, display: "Payment Amount", min_value: 0 }
      entities:
        - entity_type: claim
          id_field: CLM_ID
          property_fields:
            claim_id: CLM_ID
            service_date: CLM_FROM_DT
            through_date: CLM_THRU_DT
            amount: CLM_PMT_AMT
        - entity_type: beneficiary
          id_field: DESYNPUF_ID
          property_fields:
            hic_number: DESYNPUF_ID
        - entity_type: provider
          id_field: AT_PHYSN_NPI
          property_fields:
            npi: AT_PHYSN_NPI
        - entity_type: facility
          id_field: PRVDR_NUM
          property_fields:
            facility_id: PRVDR_NUM
      relationships:
        - relationship_type: billed_for
          source_entity_type: claim
          target_entity_type: beneficiary
        - relationship_type: submitted_by
          source_entity_type: claim
          target_entity_type: provider
        - relationship_type: performed_at
          source_entity_type: claim
          target_entity_type: facility
```

- [ ] **Step 2: Add outpatient feed**

Append a similar block named `outpatient_claims`, same DE-SynPUF outpatient schema (CLM_FROM_DT, CLM_THRU_DT, PRVDR_NUM, AT_PHYSN_NPI, CLM_PMT_AMT, etc.). Inpatient and outpatient DE-SynPUF files share the same envelope.

- [ ] **Step 3: Write test**

Create `backend/tests/config/test_desynpuf_claim_feeds_load.py`:

```python
from __future__ import annotations

from pathlib import Path

from config.loader import load_domain_config


def test_inpatient_and_outpatient_feeds_load() -> None:
    config_path = Path(__file__).parents[2] / "config" / "defaults" / "medicare_fraud_cms_desynpuf.yaml"
    config = load_domain_config(config_path)

    feed_names = {feed.name for feed in (config.records.feeds if config.records else [])}
    assert "inpatient_claims" in feed_names
    assert "outpatient_claims" in feed_names

    inpatient = next(f for f in config.records.feeds if f.name == "inpatient_claims")
    rel_types = {r.relationship_type for r in inpatient.relationships}
    assert rel_types == {"billed_for", "submitted_by", "performed_at"}
```

- [ ] **Step 4: Run test, pyright, commit**

```bash
cd backend && pytest tests/config/test_desynpuf_claim_feeds_load.py -v
git add backend/config/defaults/medicare_fraud_cms_desynpuf.yaml backend/tests/config/test_desynpuf_claim_feeds_load.py
git commit -m "feat(config): declare DE-SynPUF inpatient and outpatient claim feeds"
```

---

## Phase 4 — Tennessee Subset Materializer Tool

### Task 4.1: Create the tool package + CLI skeleton

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/sample_data/__init__.py`
- Create: `tools/sample_data/build_tennessee_subset.py`
- Test: `tools/tests/__init__.py`, `tools/tests/test_build_tennessee_subset_cli.py`

- [ ] **Step 1: Create the skeleton**

`tools/sample_data/build_tennessee_subset.py`:

```python
"""Materialize a Tennessee-filtered NPPES + DE-SynPUF subset for the demo."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Strategy = Literal["natural", "remap", "synthetic"]


@dataclass(frozen=True)
class BuildConfig:
    nppes_root: Path
    desynpuf_root: Path
    output_root: Path
    state_code: str = "TN"
    strategy: Strategy = "remap"
    sample_rate: float = 1.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Tennessee NPPES+DE-SynPUF subset.")
    parser.add_argument("--nppes-root", type=Path, default=Path("sample_data"))
    parser.add_argument("--desynpuf-root", type=Path, default=Path("sample_data/CMS"))
    parser.add_argument("--output-root", type=Path, default=Path("sample_data/CMS/tn_subset"))
    parser.add_argument("--state-code", default="TN")
    parser.add_argument("--strategy", choices=("natural", "remap", "synthetic"), default="remap")
    parser.add_argument("--sample-rate", type=float, default=1.0)
    args = parser.parse_args(argv)

    config = BuildConfig(
        nppes_root=args.nppes_root,
        desynpuf_root=args.desynpuf_root,
        output_root=args.output_root,
        state_code=args.state_code,
        strategy=args.strategy,
        sample_rate=args.sample_rate,
    )
    return build(config)


def build(config: BuildConfig) -> int:
    config.output_root.mkdir(parents=True, exist_ok=True)
    npi_set = _filter_nppes(config)
    claim_counts = _filter_desynpuf(config, npi_set)
    _write_manifest(config, npi_set, claim_counts)
    return 0


def _filter_nppes(config: BuildConfig) -> set[str]:
    raise NotImplementedError("Implemented in Task 4.2")


def _filter_desynpuf(config: BuildConfig, npi_set: set[str]) -> dict[str, int]:
    raise NotImplementedError("Implemented in Task 4.3")


def _write_manifest(
    config: BuildConfig,
    npi_set: set[str],
    claim_counts: dict[str, int],
) -> None:
    manifest = {
        "state_code": config.state_code,
        "strategy": config.strategy,
        "sample_rate": config.sample_rate,
        "npi_count": len(npi_set),
        "claim_counts": claim_counts,
    }
    (config.output_root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Write CLI smoke test**

`tools/tests/test_build_tennessee_subset_cli.py`:

```python
from __future__ import annotations

import sys

from tools.sample_data.build_tennessee_subset import main


def test_help_runs(capsys) -> None:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "--state-code" in out
    assert "--strategy" in out
```

- [ ] **Step 3: Run test, commit**

```bash
pytest tools/tests/test_build_tennessee_subset_cli.py -v
git add tools/
git commit -m "feat(tools): scaffold build_tennessee_subset CLI"
```

---

### Task 4.2: Implement NPPES streaming filter

**Files:**
- Modify: `tools/sample_data/build_tennessee_subset.py`
- Test: `tools/tests/test_filter_nppes.py` (new) + `tools/tests/fixtures/nppes_micro.csv` (new)

- [ ] **Step 1: Author micro fixture**

`tools/tests/fixtures/nppes_micro.csv` — a 10-row NPPES file with the actual column headers (you can crib them from the production file or from the documented NPPES dissemination layout). Include 6 TN rows and 4 non-TN rows.

- [ ] **Step 2: Write failing test**

```python
from __future__ import annotations

from pathlib import Path

from tools.sample_data.build_tennessee_subset import BuildConfig, _filter_nppes


def test_filter_keeps_tn_only(tmp_path: Path) -> None:
    config = BuildConfig(
        nppes_root=Path(__file__).parent / "fixtures" / "nppes_micro",  # see Step 3
        desynpuf_root=tmp_path,
        output_root=tmp_path,
    )
    npi_set = _filter_nppes(config)
    assert len(npi_set) == 6
```

- [ ] **Step 3: Set up the fixture root layout**

Make `tools/tests/fixtures/nppes_micro/` and place a file inside named matching the production glob `npidata_pfile_*.csv`. The implementation needs to find this file under the root.

- [ ] **Step 4: Implement `_filter_nppes`**

```python
import csv
from glob import glob


def _filter_nppes(config: BuildConfig) -> set[str]:
    npi_set: set[str] = set()
    state_field = "Provider Business Practice Location Address State Name"
    output_path = config.output_root / "nppes_providers_tn.csv"

    pattern = str(config.nppes_root / "npidata_pfile_*.csv")
    files = sorted(glob(pattern))
    if not files:
        raise FileNotFoundError(f"No NPPES file matched {pattern}")
    source_path = Path(files[0])

    with source_path.open("r", encoding="utf-8", newline="") as src, \
         output_path.open("w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        if reader.fieldnames is None:
            raise ValueError("NPPES file is missing a header row.")
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
        writer.writeheader()
        for row in reader:
            if row.get(state_field) == config.state_code:
                writer.writerow(row)
                npi_set.add(row["NPI"])

    return npi_set
```

- [ ] **Step 5: Run test, commit**

```bash
pytest tools/tests/test_filter_nppes.py -v
git add tools/
git commit -m "feat(tools): NPPES streaming filter keeps rows for selected state"
```

---

### Task 4.3: Implement DE-SynPUF cross-filter (default strategy: `remap`)

**Files:**
- Modify: `tools/sample_data/build_tennessee_subset.py`
- Test: `tools/tests/test_filter_desynpuf.py` (new) + fixture micro files

- [ ] **Step 1: Author micro DE-SynPUF fixtures**

Create `tools/tests/fixtures/desynpuf_micro/` with small versions of:
- `DE1_0_2010_Beneficiary_Summary_File_Sample_1.csv` (8 rows)
- `DE1_0_2008_to_2010_Carrier_Claims_Sample_1A.csv` (8 rows)
- `DE1_0_2008_to_2010_Inpatient_Claims_Sample_1.csv` (5 rows)
- `DE1_0_2008_to_2010_Outpatient_Claims_Sample_1.csv` (5 rows)

Use the real DE-SynPUF column layouts. Synthesize realistic-looking values.

- [ ] **Step 2: Write failing test**

```python
from __future__ import annotations

import json
from pathlib import Path

from tools.sample_data.build_tennessee_subset import BuildConfig, _filter_desynpuf


def test_remap_strategy_keeps_all_claims_with_tn_npi(tmp_path: Path) -> None:
    npi_set = {f"100000000{i}" for i in range(6)}  # 6 TN NPIs from the NPPES fixture
    config = BuildConfig(
        nppes_root=tmp_path,
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="remap",
    )
    counts = _filter_desynpuf(config, npi_set)

    # All carrier claims kept (remap assigns every claim to a TN NPI).
    assert counts["carrier_claims"] == 8
    assert counts["inpatient_claims"] == 5
    assert counts["outpatient_claims"] == 5

    # Beneficiary file is cross-filtered to beneficiaries referenced by kept claims.
    assert counts["beneficiaries"] <= 8
    assert (tmp_path / "desynpuf_beneficiaries_tn.csv").exists()
```

- [ ] **Step 3: Implement**

```python
import hashlib

_DESYNPUF_FILES: dict[str, tuple[str, str]] = {
    # output key -> (glob, npi_column)
    "carrier_claims": ("DE1_0_2008_to_2010_Carrier_Claims_Sample_*.csv", "PRF_PHYSN_NPI_1"),
    "inpatient_claims": ("DE1_0_2008_to_2010_Inpatient_Claims_Sample_*.csv", "AT_PHYSN_NPI"),
    "outpatient_claims": ("DE1_0_2008_to_2010_Outpatient_Claims_Sample_*.csv", "AT_PHYSN_NPI"),
}


def _filter_desynpuf(config: BuildConfig, npi_set: set[str]) -> dict[str, int]:
    tn_npis = sorted(npi_set)
    if not tn_npis:
        raise ValueError("Cannot filter DE-SynPUF without any TN NPIs.")

    counts: dict[str, int] = {}
    kept_beneficiary_ids: set[str] = set()

    for output_key, (pattern, npi_col) in _DESYNPUF_FILES.items():
        kept = 0
        output_path = config.output_root / f"desynpuf_{output_key}_tn.csv"
        files = sorted(glob(str(config.desynpuf_root / pattern)))
        if not files:
            counts[output_key] = 0
            continue

        with output_path.open("w", encoding="utf-8", newline="") as dst:
            writer: csv.DictWriter[str] | None = None
            for source in files:
                with Path(source).open("r", encoding="utf-8", newline="") as src:
                    reader = csv.DictReader(src)
                    if reader.fieldnames is None:
                        continue
                    if writer is None:
                        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
                        writer.writeheader()
                    for row in reader:
                        keep = _apply_strategy(row, npi_col, tn_npis, config.strategy, npi_set)
                        if not keep:
                            continue
                        if (bene_id := row.get("DESYNPUF_ID")):
                            kept_beneficiary_ids.add(bene_id)
                        writer.writerow(row)
                        kept += 1
        counts[output_key] = kept

    # Cross-filter beneficiaries
    counts["beneficiaries"] = _filter_beneficiaries(config, kept_beneficiary_ids)
    return counts


def _apply_strategy(
    row: dict[str, str],
    npi_col: str,
    tn_npis: list[str],
    strategy: Strategy,
    npi_set: set[str],
) -> bool:
    if strategy == "natural":
        return row.get(npi_col) in npi_set
    if strategy == "remap":
        original = row.get(npi_col, "")
        remap_index = int(hashlib.sha256(original.encode("utf-8")).hexdigest(), 16) % len(tn_npis)
        row[npi_col] = tn_npis[remap_index]
        return True
    if strategy == "synthetic":
        # Pure random assignment — deterministic per (row, claim_id) so re-runs are reproducible.
        seed = row.get("CLM_ID", "") + npi_col
        idx = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(tn_npis)
        row[npi_col] = tn_npis[idx]
        return True
    raise ValueError(f"Unknown strategy: {strategy}")


def _filter_beneficiaries(config: BuildConfig, kept_ids: set[str]) -> int:
    pattern = str(config.desynpuf_root / "DE1_0_*_Beneficiary_Summary_File_Sample_*.csv")
    files = sorted(glob(pattern))
    if not files:
        return 0
    output_path = config.output_root / "desynpuf_beneficiaries_tn.csv"
    total_kept = 0
    with output_path.open("w", encoding="utf-8", newline="") as dst:
        writer: csv.DictWriter[str] | None = None
        for source in files:
            with Path(source).open("r", encoding="utf-8", newline="") as src:
                reader = csv.DictReader(src)
                if reader.fieldnames is None:
                    continue
                if writer is None:
                    writer = csv.DictWriter(dst, fieldnames=reader.fieldnames)
                    writer.writeheader()
                for row in reader:
                    if row.get("DESYNPUF_ID") in kept_ids:
                        writer.writerow(row)
                        total_kept += 1
    return total_kept
```

- [ ] **Step 4: Run test, commit**

```bash
pytest tools/tests/test_filter_desynpuf.py -v
git add tools/
git commit -m "feat(tools): DE-SynPUF cross-filter with natural/remap/synthetic strategies"
```

---

### Task 4.4: Manifest content + idempotency test

**Files:**
- Modify: `tools/sample_data/build_tennessee_subset.py` (`_write_manifest`)
- Test: `tools/tests/test_manifest_and_idempotency.py` (new)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import json
from pathlib import Path

from tools.sample_data.build_tennessee_subset import BuildConfig, build


def test_manifest_captures_strategy_and_counts(tmp_path: Path) -> None:
    config = BuildConfig(
        nppes_root=Path(__file__).parent / "fixtures" / "nppes_micro",
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="remap",
    )
    assert build(config) == 0
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert manifest["state_code"] == "TN"
    assert manifest["strategy"] == "remap"
    assert manifest["npi_count"] == 6
    assert "carrier_claims" in manifest["claim_counts"]


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    config = BuildConfig(
        nppes_root=Path(__file__).parent / "fixtures" / "nppes_micro",
        desynpuf_root=Path(__file__).parent / "fixtures" / "desynpuf_micro",
        output_root=tmp_path,
        strategy="remap",
    )
    build(config)
    first_bytes = (tmp_path / "nppes_providers_tn.csv").read_bytes()
    build(config)
    second_bytes = (tmp_path / "nppes_providers_tn.csv").read_bytes()
    assert first_bytes == second_bytes
```

- [ ] **Step 2: Verify the implementation already supports both (no impl change should be needed if `_write_manifest` was implemented per Task 4.1)**

- [ ] **Step 3: Run tests, commit**

```bash
pytest tools/tests/test_manifest_and_idempotency.py -v
git add tools/
git commit -m "test(tools): cover MANIFEST.json content and re-run idempotency"
```

---

## Phase 5 — Ollama LLM Adapter + Fallback Chain

### Task 5.1: Add `OllamaLlmClient` adapter

**Files:**
- Create: `backend/llm/adapters/ollama_adapter.py`
- Test: `backend/tests/llm/test_ollama_adapter.py` (new)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from llm.adapters.ollama_adapter import OllamaLlmClient
from llm.exceptions import LlmProviderError
from llm.models import ChatMessage, GenerationRequest, MessageRole


def _request() -> GenerationRequest:
    return GenerationRequest(
        request_id="r1",
        model_name="llama3.1:8b",
        messages=[ChatMessage(role=MessageRole.USER, content="hello")],
    )


def test_generate_calls_ollama_chat_endpoint() -> None:
    response = httpx.Response(
        status_code=200,
        json={"message": {"content": "hi there"}, "done": True},
    )
    with patch.object(httpx.Client, "post", return_value=response) as post:
        client = OllamaLlmClient(base_url="http://localhost:11434")
        result = client.generate(_request())

    assert result.completion == "hi there"
    assert result.metadata.provider == "ollama"
    assert result.metadata.model_name == "llama3.1:8b"
    args, kwargs = post.call_args
    assert args[0].endswith("/api/chat")
    assert kwargs["json"]["model"] == "llama3.1:8b"


def test_generate_raises_on_5xx() -> None:
    response = httpx.Response(status_code=503, text="overloaded")
    with patch.object(httpx.Client, "post", return_value=response):
        client = OllamaLlmClient(base_url="http://localhost:11434")
        with pytest.raises(LlmProviderError):
            client.generate(_request())
```

- [ ] **Step 2: Implement**

```python
"""LLM client adapter for a local Ollama HTTP endpoint."""

from __future__ import annotations

import httpx

from llm.exceptions import LlmProviderError
from llm.models import CompletionMetadata, GenerationRequest, GenerationResult


class OllamaLlmClient:
    """Generate completions against an Ollama HTTP API."""

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout_seconds)

    def generate(self, request: GenerationRequest) -> GenerationResult:
        payload = {
            "model": request.model_name,
            "messages": [{"role": message.role.value, "content": message.content} for message in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        try:
            response = self._client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.HTTPError as exc:
            raise LlmProviderError(f"Ollama transport error: {exc}") from exc

        if response.status_code >= 500:
            raise LlmProviderError(
                f"Ollama returned {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise LlmProviderError(
                f"Ollama rejected request ({response.status_code}): {response.text[:200]}"
            )

        body = response.json()
        completion = body.get("message", {}).get("content", "")
        if not completion.strip():
            raise LlmProviderError("Ollama returned an empty completion.")

        return GenerationResult(
            request_id=request.request_id,
            completion=completion,
            metadata=CompletionMetadata(
                provider="ollama",
                model_name=request.model_name,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            ),
        )

    def close(self) -> None:
        self._client.close()


__all__ = ["OllamaLlmClient"]
```

- [ ] **Step 3: Run test, pyright, commit**

```bash
cd backend && pytest tests/llm/test_ollama_adapter.py -v && pyright llm
git add backend/llm/adapters/ollama_adapter.py backend/tests/llm/test_ollama_adapter.py
git commit -m "feat(llm): add OllamaLlmClient adapter"
```

---

### Task 5.2: Add `FallbackLlmClient` decorator

**Files:**
- Create: `backend/llm/adapters/fallback.py`
- Test: `backend/tests/llm/test_fallback_client.py` (new)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm.adapters.fallback import FallbackLlmClient
from llm.exceptions import LlmProviderError
from llm.models import ChatMessage, CompletionMetadata, GenerationRequest, GenerationResult, MessageRole


def _request() -> GenerationRequest:
    return GenerationRequest(
        request_id="r1",
        model_name="m",
        messages=[ChatMessage(role=MessageRole.USER, content="hi")],
    )


def _result(provider: str) -> GenerationResult:
    return GenerationResult(
        request_id="r1",
        completion="ok",
        metadata=CompletionMetadata(provider=provider, model_name="m", temperature=0.2, max_tokens=128),
    )


def test_primary_success_skips_fallback() -> None:
    primary = MagicMock()
    primary.generate.return_value = _result("primary")
    fallback = MagicMock()

    client = FallbackLlmClient(primary=primary, fallbacks=[fallback])
    result = client.generate(_request())

    assert result.metadata.provider == "primary"
    fallback.generate.assert_not_called()


def test_primary_failure_uses_first_fallback() -> None:
    primary = MagicMock()
    primary.generate.side_effect = LlmProviderError("primary down")
    fallback = MagicMock()
    fallback.generate.return_value = _result("fallback-1")

    client = FallbackLlmClient(primary=primary, fallbacks=[fallback])
    result = client.generate(_request())

    assert result.metadata.provider == "fallback-1"
    fallback.generate.assert_called_once()


def test_all_failures_raise_chain_exhausted() -> None:
    primary = MagicMock()
    primary.generate.side_effect = LlmProviderError("primary down")
    fallback = MagicMock()
    fallback.generate.side_effect = LlmProviderError("fallback down")

    client = FallbackLlmClient(primary=primary, fallbacks=[fallback])
    with pytest.raises(LlmProviderError) as excinfo:
        client.generate(_request())
    assert "exhausted" in str(excinfo.value).lower()
```

- [ ] **Step 2: Implement**

```python
"""Fallback decorator that tries an ordered list of llm clients."""

from __future__ import annotations

import logging

from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmProviderError
from llm.models import GenerationRequest, GenerationResult


logger = logging.getLogger(__name__)


class FallbackLlmClient:
    """Try ``primary``; on transient failure try each entry of ``fallbacks`` in order."""

    def __init__(
        self,
        *,
        primary: LlmClientProtocol,
        fallbacks: list[LlmClientProtocol],
    ) -> None:
        self._primary = primary
        self._fallbacks = fallbacks

    def generate(self, request: GenerationRequest) -> GenerationResult:
        chain: list[LlmClientProtocol] = [self._primary, *self._fallbacks]
        last_error: Exception | None = None
        for index, client in enumerate(chain):
            try:
                return client.generate(request)
            except LlmProviderError as exc:
                last_error = exc
                logger.warning(
                    "llm provider %d/%d failed: %s",
                    index + 1, len(chain), exc,
                )
        raise LlmProviderError(
            f"All {len(chain)} llm providers exhausted."
        ) from last_error


__all__ = ["FallbackLlmClient"]
```

- [ ] **Step 3: Run test, pyright, commit**

```bash
cd backend && pytest tests/llm/test_fallback_client.py -v && pyright llm
git add backend/llm/adapters/fallback.py backend/tests/llm/test_fallback_client.py
git commit -m "feat(llm): add FallbackLlmClient decorator"
```

---

### Task 5.3: Add `"ollama"` provider to `LlmConfig` + add `fallback` field

**Files:**
- Modify: `backend/config/schema.py:116-123` (`LlmConfig`)
- Test: `backend/tests/config/test_llm_config_ollama.py` (new)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.schema import LlmConfig


def test_ollama_is_accepted_as_provider() -> None:
    config = LlmConfig(provider="ollama", model="llama3.1:8b")
    assert config.provider == "ollama"


def test_fallback_chain_is_accepted() -> None:
    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        fallback=LlmConfig(provider="ollama", model="llama3.1:8b"),
    )
    assert config.fallback is not None
    assert config.fallback.provider == "ollama"


def test_unknown_provider_rejected() -> None:
    with pytest.raises(ValidationError):
        LlmConfig(provider="vllm")
```

- [ ] **Step 2: Implement**

In `backend/config/schema.py`:

```python
class LlmConfig(BaseModel):
    """Configuration for selecting the LLM provider and model."""

    provider: Literal["openai", "anthropic", "local", "ollama"] = "local"
    model: str = "local-default"
    api_key_env_var: str | None = None
    base_url: str | None = None  # Used by ollama; ignored by other providers.
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
    fallback: "LlmConfig | None" = None
```

- [ ] **Step 3: Run test, pyright, commit**

```bash
cd backend && pytest tests/config/test_llm_config_ollama.py -v && pyright config
git add backend/config/schema.py backend/tests/config/test_llm_config_ollama.py
git commit -m "feat(config): add ollama provider and fallback chain to LlmConfig"
```

---

### Task 5.4: Wire Ollama + Fallback into the LLM factory

**Files:**
- Modify: `backend/llm/factory.py` (find the factory file with `grep -rn "create_llm_client\|build_llm_client" backend/llm/`)
- Test: `backend/tests/llm/test_factory_chain.py` (new)

- [ ] **Step 1: Identify factory**

```bash
cd backend && grep -rn "openai\|anthropic" llm --include="*.py" | grep -i factory
```

If a factory module does not yet exist, the wiring may live in `backend/api/dependencies.py`. The principle is the same — extend the construction site.

- [ ] **Step 2: Write failing test**

```python
from __future__ import annotations

from config.schema import LlmConfig
from llm.factory import create_llm_client  # adapt to real factory name
from llm.adapters.ollama_adapter import OllamaLlmClient
from llm.adapters.fallback import FallbackLlmClient
from llm.adapters.openai_adapter import OpenAiLlmClient  # adapt to real class name


def test_factory_returns_ollama_when_selected(monkeypatch) -> None:
    config = LlmConfig(provider="ollama", model="llama3.1:8b", base_url="http://localhost:11434")
    client = create_llm_client(config)
    assert isinstance(client, OllamaLlmClient)


def test_factory_wraps_with_fallback_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = LlmConfig(
        provider="openai",
        model="gpt-4o-mini",
        api_key_env_var="OPENAI_API_KEY",
        fallback=LlmConfig(provider="ollama", model="llama3.1:8b"),
    )
    client = create_llm_client(config)
    assert isinstance(client, FallbackLlmClient)
```

- [ ] **Step 3: Implement**

Extend the factory:

```python
def create_llm_client(config: LlmConfig) -> LlmClientProtocol:
    primary = _instantiate_provider(config)
    if config.fallback is None:
        return primary
    fallbacks = [_instantiate_provider(config.fallback)]
    return FallbackLlmClient(primary=primary, fallbacks=fallbacks)


def _instantiate_provider(config: LlmConfig) -> LlmClientProtocol:
    if config.provider == "ollama":
        return OllamaLlmClient(base_url=config.base_url or "http://localhost:11434")
    if config.provider == "openai":
        return OpenAiLlmClient(...)  # existing construction
    if config.provider == "anthropic":
        return AnthropicLlmClient(...)
    if config.provider == "local":
        return InMemoryLlmClient(...)
    raise LlmConfigurationError(f"Unknown llm provider: {config.provider}")
```

(Substitute real class names from `backend/llm/adapters/`.)

- [ ] **Step 4: Run test, pyright, commit**

```bash
cd backend && pytest tests/llm/test_factory_chain.py -v && pyright llm
git add backend/llm backend/tests/llm/test_factory_chain.py
git commit -m "feat(llm): wire Ollama + FallbackLlmClient into the llm factory"
```

---

### Task 5.5: Declare `llm.fallback.provider: ollama` in `medicare_fraud_cms_desynpuf.yaml`

**Files:**
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`
- Test: `backend/tests/config/test_medicare_fraud_llm_chain.py` (new)

- [ ] **Step 1: Add the llm block to the YAML**

Append (or replace if a stub exists):

```yaml
llm:
  provider: openai
  model: gpt-4o-mini
  api_key_env_var: OPENAI_API_KEY
  temperature: 0.2
  max_tokens: 4096
  fallback:
    provider: ollama
    model: llama3.1:8b
    base_url: http://localhost:11434
    temperature: 0.2
    max_tokens: 4096
```

- [ ] **Step 2: Test it loads**

```python
from __future__ import annotations

from pathlib import Path

from config.loader import load_domain_config


def test_llm_chain_loads_with_openai_primary_and_ollama_fallback() -> None:
    path = Path(__file__).parents[2] / "config" / "defaults" / "medicare_fraud_cms_desynpuf.yaml"
    config = load_domain_config(path)

    assert config.llm is not None
    assert config.llm.provider == "openai"
    assert config.llm.fallback is not None
    assert config.llm.fallback.provider == "ollama"
```

- [ ] **Step 3: Run, commit**

```bash
cd backend && pytest tests/config/test_medicare_fraud_llm_chain.py -v
git add backend/config/defaults/medicare_fraud_cms_desynpuf.yaml backend/tests/config/test_medicare_fraud_llm_chain.py
git commit -m "feat(config): wire openai primary + ollama fallback in medicare_fraud config"
```

---

## Phase 6 — `LlmDocumentExtractor`

### Task 6.1: Add `LlmDocumentExtractor` skeleton + fallback to pattern extractor

**Files:**
- Modify: `backend/ingestion/extractor.py` (add new class alongside `PatternDocumentExtractor`)
- Modify: `backend/ingestion/factory.py` (or wherever `create_document_extractor` lives)
- Test: `backend/tests/ingestion/test_llm_extractor.py` (new)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import json
from unittest.mock import MagicMock

from config.schema import EntityDefinition, PropertyDefinition, PropertyType, RelationshipDefinition
from ingestion.chunker import ChunkingResult
from ingestion.extractor import LlmDocumentExtractor
from ingestion.models import Chunk, ChunkMetadata
from llm.models import CompletionMetadata, GenerationResult


def _chunking_result() -> ChunkingResult:
    return ChunkingResult(
        id="cr-1",
        source_document_id="doc-1",
        parsed_document_id="pd-1",
        chunks=[
            Chunk(
                id="chunk-1",
                content="Provider NPI 1234567890 specializes in Cardiology.",
                metadata=ChunkMetadata(start_offset=0, end_offset=51),
            ),
        ],
    )


def _entity_defs() -> list[EntityDefinition]:
    return [
        EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={
                "npi": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True),
                "specialty": PropertyDefinition(type=PropertyType.STRING, display="Specialty"),
            },
        ),
    ]


def test_llm_extractor_returns_validated_entities() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion=json.dumps({
            "entities": [
                {"type": "provider", "properties": {"npi": "1234567890", "specialty": "Cardiology"}},
            ],
            "relationships": [],
        }),
        metadata=CompletionMetadata(provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512),
    )

    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert len(result.candidate_entities) == 1
    assert result.candidate_entities[0].type == "provider"
    assert result.candidate_entities[0].properties["npi"] == "1234567890"


def test_llm_extractor_drops_entities_failing_required_property() -> None:
    llm_client = MagicMock()
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion=json.dumps({
            "entities": [
                {"type": "provider", "properties": {"specialty": "Cardiology"}},  # missing npi
            ],
            "relationships": [],
        }),
        metadata=CompletionMetadata(provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512),
    )

    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
    )
    result = extractor.extract_document(_chunking_result())

    assert result.candidate_entities == []
    assert any("required" in w for w in result.warnings)


def test_llm_extractor_dedupes_by_natural_key_across_chunks() -> None:
    llm_client = MagicMock()
    # Both chunks return the same provider entity.
    llm_client.generate.return_value = GenerationResult(
        request_id="r1",
        completion=json.dumps({
            "entities": [{"type": "provider", "properties": {"npi": "1234567890"}}],
            "relationships": [],
        }),
        metadata=CompletionMetadata(provider="openai", model_name="gpt-4o-mini", temperature=0.2, max_tokens=512),
    )

    chunking = ChunkingResult(
        id="cr-1",
        source_document_id="doc-1",
        parsed_document_id="pd-1",
        chunks=[
            Chunk(id="c1", content="first mention NPI 1234567890.", metadata=ChunkMetadata(start_offset=0, end_offset=30)),
            Chunk(id="c2", content="second mention NPI 1234567890.", metadata=ChunkMetadata(start_offset=30, end_offset=60)),
        ],
    )
    extractor = LlmDocumentExtractor(
        entity_definitions=_entity_defs(),
        relationship_definitions=[],
        llm_client=llm_client,
        natural_keys={"provider": ["npi"]},
    )
    result = extractor.extract_document(chunking)

    assert len(result.candidate_entities) == 1
```

- [ ] **Step 2: Implement**

Add to `backend/ingestion/extractor.py`:

```python
import json
import logging
from typing import Any

from llm.adapters.protocols import LlmClientProtocol
from llm.exceptions import LlmProviderError
from llm.models import ChatMessage, GenerationRequest, MessageRole
from shared.utils import generate_id


_LOG = logging.getLogger(__name__)


class LlmDocumentExtractor:
    """Extract entities and relationships per chunk via an LlmClient."""

    def __init__(
        self,
        entity_definitions: list[EntityDefinition],
        relationship_definitions: list[RelationshipDefinition] | None = None,
        *,
        llm_client: LlmClientProtocol,
        natural_keys: dict[str, list[str]] | None = None,
        extraction_method: str = "llm_v1",
        model_name: str = "extractor-model",
    ) -> None:
        self._entity_definitions = entity_definitions
        self._relationship_definitions = relationship_definitions or []
        self._client = llm_client
        self._natural_keys = natural_keys or {}
        self._extraction_method = extraction_method
        self._model_name = model_name

    def extract_document(self, chunking_result: ChunkingResult) -> ExtractionResult:
        all_candidates: list[CandidateEntity] = []
        all_relationships: list[CandidateRelationship] = []
        warnings: list[str] = []
        seen_natural_keys: dict[str, set[tuple[object, ...]]] = {}

        for chunk in chunking_result.chunks:
            chunk_candidates, chunk_warnings = self._extract_chunk(chunking_result, chunk)
            warnings.extend(chunk_warnings)

            for candidate in chunk_candidates:
                if self._is_duplicate(candidate, seen_natural_keys):
                    continue
                all_candidates.append(candidate)

        # Relationships are emitted per-chunk and naturally dedupe by tuple.
        all_relationships.extend(
            self._extract_relationships(chunking_result, all_candidates)
        )

        return ExtractionResult(
            id=generate_id(),
            source_document_id=chunking_result.source_document_id,
            parsed_document_id=chunking_result.parsed_document_id,
            chunks=chunking_result.chunks,
            candidate_entities=all_candidates,
            candidate_relationships=all_relationships,
            warnings=warnings,
        )

    # ---- internal helpers ----

    def _extract_chunk(
        self,
        chunking_result: ChunkingResult,
        chunk: Chunk,
    ) -> tuple[list[CandidateEntity], list[str]]:
        prompt = self._build_prompt(chunk.content)
        try:
            result = self._client.generate(
                GenerationRequest(
                    request_id=generate_id(),
                    knowledge_base_id=None,
                    messages=[
                        ChatMessage(role=MessageRole.SYSTEM, content=prompt["system"]),
                        ChatMessage(role=MessageRole.USER, content=prompt["user"]),
                    ],
                    model_name=self._model_name,
                    temperature=0.1,
                    max_tokens=1024,
                )
            )
        except LlmProviderError as exc:
            return [], [f"LLM extraction failed for chunk {chunk.id}: {exc}"]

        try:
            payload = json.loads(result.completion)
        except json.JSONDecodeError as exc:
            return [], [f"LLM returned non-JSON for chunk {chunk.id}: {exc}"]

        candidates: list[CandidateEntity] = []
        warnings: list[str] = []
        for raw_entity in payload.get("entities", []):
            entity, warning = self._build_candidate(chunking_result, chunk, raw_entity)
            if entity is not None:
                candidates.append(entity)
            elif warning is not None:
                warnings.append(warning)
        return candidates, warnings

    def _build_prompt(self, content: str) -> dict[str, str]:
        entity_schemas = [
            {
                "type": d.name,
                "properties": {p: {"required": pdef.required, "type": pdef.type.value}
                               for p, pdef in d.properties.items()},
            }
            for d in self._entity_definitions
        ]
        relationship_schemas = [
            {"type": r.name, "source": r.source, "target": r.target}
            for r in self._relationship_definitions
        ]
        system = (
            "You extract structured entities and relationships from text. "
            "Output strict JSON of the form "
            '{"entities": [{"type": "...", "properties": {...}}], '
            '"relationships": [{"type": "...", "source_index": 0, "target_index": 1}]}. '
            "Use only entity types listed in the schema. Omit fields you cannot find."
        )
        user = (
            f"Entity schemas: {json.dumps(entity_schemas)}\n"
            f"Relationship schemas: {json.dumps(relationship_schemas)}\n\n"
            f"Text:\n{content}\n\n"
            "Return JSON only."
        )
        return {"system": system, "user": user}

    def _build_candidate(
        self,
        chunking_result: ChunkingResult,
        chunk: Chunk,
        raw: dict[str, Any],
    ) -> tuple[CandidateEntity | None, str | None]:
        entity_type = raw.get("type")
        properties = raw.get("properties", {})
        if not isinstance(entity_type, str) or not isinstance(properties, dict):
            return None, f"Skipping malformed entity in chunk {chunk.id}."

        defn = next((d for d in self._entity_definitions if d.name == entity_type), None)
        if defn is None:
            return None, f"Unknown entity type '{entity_type}' in chunk {chunk.id}."

        missing_required = [
            name for name, pdef in defn.properties.items()
            if pdef.required and name not in properties
        ]
        if missing_required:
            return None, (
                f"Entity '{entity_type}' in chunk {chunk.id} is missing required "
                f"properties: {missing_required}"
            )

        return CandidateEntity(
            id=generate_id(),
            source_document_id=chunking_result.source_document_id,
            chunk_id=chunk.id,
            type=entity_type,
            properties=properties,
            confidence=0.8,
            extraction_method=self._extraction_method,
            evidence=[],
            metadata={"llm_model": self._model_name},
        ), None

    def _is_duplicate(
        self,
        candidate: CandidateEntity,
        seen: dict[str, set[tuple[object, ...]]],
    ) -> bool:
        key_fields = self._natural_keys.get(candidate.type)
        if not key_fields:
            return False
        try:
            key = tuple(candidate.properties[f] for f in key_fields)
        except KeyError:
            return False
        bucket = seen.setdefault(candidate.type, set())
        if key in bucket:
            return True
        bucket.add(key)
        return False

    def _extract_relationships(
        self,
        chunking_result: ChunkingResult,
        candidates: list[CandidateEntity],
    ) -> list[CandidateRelationship]:
        # Minimal first cut: emit a relationship between any two candidates that
        # appear in the same chunk and whose types match a relationship definition.
        # This mirrors PatternDocumentExtractor's intra-chunk behavior.
        relationships: list[CandidateRelationship] = []
        for chunk in chunking_result.chunks:
            chunk_candidates = [c for c in candidates if c.chunk_id == chunk.id]
            for rel_def in self._relationship_definitions:
                sources = [c for c in chunk_candidates if c.type == rel_def.source]
                targets = [c for c in chunk_candidates if c.type == rel_def.target]
                for source in sources:
                    for target in targets:
                        if source.id == target.id:
                            continue
                        relationships.append(
                            CandidateRelationship(
                                id=generate_id(),
                                source_document_id=chunking_result.source_document_id,
                                chunk_id=chunk.id,
                                type=rel_def.name,
                                source_candidate_id=source.id,
                                target_candidate_id=target.id,
                                confidence=min(source.confidence, target.confidence),
                                extraction_method=self._extraction_method,
                                evidence=[],
                                metadata={},
                            )
                        )
        return relationships
```

- [ ] **Step 3: Update `create_document_extractor` to choose between pattern and LLM**

```python
def create_document_extractor(
    entity_definitions: list[EntityDefinition],
    relationship_definitions: list[RelationshipDefinition] | None = None,
    *,
    llm_client: LlmClientProtocol | None = None,
    natural_keys: dict[str, list[str]] | None = None,
) -> PatternDocumentExtractor | LlmDocumentExtractor:
    if llm_client is None:
        return PatternDocumentExtractor(entity_definitions, relationship_definitions)
    return LlmDocumentExtractor(
        entity_definitions,
        relationship_definitions,
        llm_client=llm_client,
        natural_keys=natural_keys,
    )
```

Wire the construction site (likely in `backend/api/dependencies.py` or `backend/agent/coordinator.py` worker init) to pass the configured `llm_client` from the factory.

- [ ] **Step 4: Run tests, pyright, commit**

```bash
cd backend && pytest tests/ingestion/test_llm_extractor.py -v && pyright ingestion
git add backend/ingestion backend/tests/ingestion/test_llm_extractor.py
git commit -m "feat(ingestion): add LlmDocumentExtractor with schema-driven prompts"
```

---

### Task 6.2: Add two markdown policy fixtures for integration testing

**Files:**
- Create: `backend/tests/ingestion/fixtures/policies/policy_001_inpatient_billing.md`
- Create: `backend/tests/ingestion/fixtures/policies/policy_002_provider_exclusion.md`

- [ ] **Step 1: Author fixtures**

`policy_001_inpatient_billing.md`:

```markdown
# Policy POL-2024-INPATIENT-001 — Inpatient Billing Limits

Effective 2024-01-01. Governs CPT codes 99221, 99222, 99223.

Inpatient evaluation-and-management claims must be submitted by an attending
physician with NPI on file. Maximum reimbursement amount is $250.00 per
claim. Cites 42 CFR 410.32.

Provider NPI 1234567890 is the example contact.
```

`policy_002_provider_exclusion.md`:

```markdown
# Policy POL-2024-EXCLUSION-002 — Excluded Provider Reporting

Effective 2024-03-15. Governs reporting of providers who appear on the OIG
exclusion list. Provider NPI 9876543210 was added to the exclusion list on
2024-02-01. Claims submitted by excluded providers must be denied.

Cites 42 CFR 1001.1901.
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/ingestion/fixtures/policies/
git commit -m "test(ingestion): add two markdown policy fixtures for extractor integration"
```

---

### Task 6.3: Integration test — LLM extractor against Ollama (skipped without service)

**Files:**
- Create: `backend/tests/ingestion/test_documents_e2e_with_ollama.py`

- [ ] **Step 1: Write the integration test**

```python
"""Integration: extract from a markdown policy fixture using a live Ollama."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from config.schema import LlmConfig
from ingestion.extractor import LlmDocumentExtractor
from ingestion.chunker import RecursiveChunker, ChunkingConfig as ChunkConfig
from ingestion.parsers.markdown import parse_markdown  # adapt to real parser API
from llm.factory import create_llm_client
from shared.types import EntityDefinition, PropertyDefinition, PropertyType


pytestmark = pytest.mark.integration


def _ollama_reachable() -> bool:
    url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/tags"
    try:
        return httpx.get(url, timeout=2.0).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not reachable")
def test_extract_policy_fixture_with_ollama() -> None:
    fixture = Path(__file__).parent / "fixtures" / "policies" / "policy_001_inpatient_billing.md"
    parsed = parse_markdown(fixture.read_text(), source_document_id="doc-1")
    chunker = RecursiveChunker(ChunkConfig())
    chunks = chunker.chunk(parsed)

    config = LlmConfig(provider="ollama", model="llama3.1:8b", temperature=0.0)
    client = create_llm_client(config)

    entity_defs = [
        EntityDefinition(
            name="provider",
            display_label="Provider",
            icon="stethoscope",
            properties={"npi": PropertyDefinition(type=PropertyType.STRING, display="NPI", required=True)},
        ),
    ]
    extractor = LlmDocumentExtractor(
        entity_definitions=entity_defs,
        llm_client=client,
        natural_keys={"provider": ["npi"]},
    )
    result = extractor.extract_document(chunks)
    npis = {c.properties.get("npi") for c in result.candidate_entities}
    # The fixture references NPI 1234567890; assert the extractor catches it.
    assert "1234567890" in npis
```

- [ ] **Step 2: Run (will skip if Ollama isn't running)**

```bash
cd backend && pytest tests/ingestion/test_documents_e2e_with_ollama.py -v -m integration
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/ingestion/test_documents_e2e_with_ollama.py
git commit -m "test(ingestion): integration test for LLM extractor against live Ollama"
```

---

## Phase 7 — End-to-End Verification + Documentation

### Task 7.1: Full E2E test exercising both flows in one KB

**Files:**
- Modify: `backend/tests/e2e/test_full_pipeline.py`

- [ ] **Step 1: Add the combined test**

```python
def test_e2e_records_and_documents_populate_one_kb(api_client, graph_service, vector_service) -> None:
    create = api_client.post("/knowledgebases", json={"name": "tn-e2e-combined", "description": ""})
    kb_id = create.json()["id"]

    # Records side
    fixture_csv = Path(__file__).parent / "fixtures" / "tiny_carrier_claims.csv"
    with fixture_csv.open("rb") as fh:
        api_client.post(
            f"/records/{kb_id}/files",
            files={"file": ("tiny_carrier_claims.csv", fh, "text/csv")},
            data={"feed_name": "carrier_claims_a"},
        )

    # Documents side
    fixture_md = Path(__file__).parents[1] / "ingestion" / "fixtures" / "policies" / "policy_001_inpatient_billing.md"
    with fixture_md.open("rb") as fh:
        api_client.post(
            f"/knowledgebases/{kb_id}/documents",
            files=[("files", ("policy_001_inpatient_billing.md", fh, "text/markdown"))],
        )

    drain_worker_events(timeout_seconds=60)

    metrics = graph_service.compute_metrics(kb_id)
    assert metrics.entity_count >= 7  # records (7) + at least one document-extracted provider
    assert vector_service.count(kb_id) >= 7
```

- [ ] **Step 2: Run, commit**

```bash
cd backend && pytest tests/e2e/test_full_pipeline.py::test_e2e_records_and_documents_populate_one_kb -v
git add backend/tests/e2e/test_full_pipeline.py
git commit -m "test(e2e): combined records+documents flow populates one KB"
```

---

### Task 7.2: `make demo-tn-subset` convenience target

**Files:**
- Modify: `Makefile` (root)

- [ ] **Step 1: Add target**

In `Makefile`, append:

```makefile
.PHONY: demo-tn-subset
demo-tn-subset:
	python -m tools.sample_data.build_tennessee_subset \
		--nppes-root sample_data \
		--desynpuf-root sample_data/CMS \
		--output-root sample_data/CMS/tn_subset
	scripts/demo_ingest_tn_subset.sh
```

- [ ] **Step 2: Add the driver script**

Create `scripts/demo_ingest_tn_subset.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

API="${CHILI_API_URL:-http://localhost:8000}"

KB_RESPONSE=$(curl -s -X POST "$API/knowledgebases" \
  -H 'Content-Type: application/json' \
  -d '{"name":"TN Demo","description":"Tennessee NPPES+DE-SynPUF subset"}')
KB_ID=$(echo "$KB_RESPONSE" | python -c "import json, sys; print(json.load(sys.stdin)['id'])")
echo "Created KB $KB_ID"

upload() {
  local feed="$1"
  local path="$2"
  curl -s -X POST "$API/records/$KB_ID/files" \
    -F "file=@$path" \
    -F "feed_name=$feed" \
    | python -m json.tool
}

upload "nppes_providers" sample_data/CMS/tn_subset/nppes_providers_tn.csv
upload "inpatient_claims" sample_data/CMS/tn_subset/desynpuf_inpatient_claims_tn.csv
upload "outpatient_claims" sample_data/CMS/tn_subset/desynpuf_outpatient_claims_tn.csv
upload "carrier_claims_a" sample_data/CMS/tn_subset/desynpuf_carrier_claims_tn.csv
upload "beneficiary_2010" sample_data/CMS/tn_subset/desynpuf_beneficiaries_tn.csv

echo "Done. KB ID: $KB_ID"
```

Make it executable: `chmod +x scripts/demo_ingest_tn_subset.sh`.

- [ ] **Step 3: Commit**

```bash
git add Makefile scripts/demo_ingest_tn_subset.sh
git commit -m "feat(make): demo-tn-subset target builds + uploads the TN subset"
```

---

### Task 7.3: README + architecture doc updates

**Files:**
- Modify: `README.md` (root)
- Modify: `backend/README.md`
- Modify: `backend/ingestion/README.md`
- Modify: `backend/records/README.md`
- Modify: `backend/graph/README.md`
- Modify: `backend/vectorstore/README.md`
- Modify: `backend/llm/README.md`
- Modify: `backend/agent/README.md`
- Modify: `docs/architecture.md`
- Modify: `CLAUDE.md` (adapter inventory)

- [ ] **Step 1: For each README**

Add a short subsection describing what changed in this initiative:
- `backend/llm/README.md`: list `OllamaLlmClient` as a supported adapter; document `LlmConfig.provider="ollama"` and `LlmConfig.fallback`.
- `backend/ingestion/README.md`: document `LlmDocumentExtractor` with schema-driven prompts and natural-key dedup; describe the fallback to `PatternDocumentExtractor` when no LLM is configured.
- `backend/graph/README.md`: document the new `delete_by_source_document` method on `GraphService`/`GraphRepository` and the provenance metadata contract on entities/relationships.
- `backend/vectorstore/README.md`: document `delete_by_source_document`.
- `backend/records/README.md`: document the new NPPES + DE-SynPUF inpatient/outpatient feeds available in the medicare_fraud config; reference the TN subset tool.
- `backend/agent/README.md`: document the new `handle_knowledge_base_deleted` retry handler and the embed-and-index step now part of `handle_records_ingested`.
- `backend/README.md`: add the TN subset tool + `make demo-tn-subset` to the "Common Commands" section.
- `README.md`: add a "Demo: Tennessee Medicare subset" section linking to the spec and the make target.

- [ ] **Step 2: Update `docs/architecture.md`**

In the relevant pipeline section, add notes for: provenance metadata fields on `Entity`/`Relationship`, the 207 KB delete cascade, the document re-upload semantics, the LLM extractor + fallback chain, and the NPPES/DE-SynPUF feeds. Keep the additions brief — link out to the spec for detail.

- [ ] **Step 3: Update `CLAUDE.md`**

In the section that lists adapter inventories, add Ollama under the LLM adapters list (alongside in-memory, OpenAI, Anthropic). Confirm `"ollama"` is now in the `LlmConfig.provider` literal so the existing "roadmap adapter" rule is satisfied.

- [ ] **Step 4: Commit**

```bash
git add README.md backend/README.md backend/ingestion/README.md backend/records/README.md backend/graph/README.md backend/vectorstore/README.md backend/llm/README.md backend/agent/README.md docs/architecture.md CLAUDE.md
git commit -m "docs: document TN demo + LLM extractor + Ollama adapter + cascade delete"
```

---

### Task 7.4: Final acceptance — full test suite + coverage gate + pyright

- [ ] **Step 1: Full backend test suite**

```bash
cd backend && pytest --cov --cov-fail-under=85
```

Expected: all green, coverage ≥85% per package.

- [ ] **Step 2: Pyright strict on the include list**

```bash
cd backend && pyright
```

Expected: 0 errors.

- [ ] **Step 3: Ruff**

```bash
cd backend && ruff check .
```

Expected: 0 issues. If lint fails, fix in place and re-run.

- [ ] **Step 4: Frontend lint + type + tests (only if any frontend code was touched in this plan; it was not, but verify nothing broke)**

```bash
cd chili_app && npm run lint && npm run build && npm run test:run
```

Expected: 0 errors. (Skip if nothing in `chili_app/` was touched — the plan does not modify frontend code.)

- [ ] **Step 5: Bring up the dev stack and smoke-run the demo**

```bash
make dev
# wait for services to be healthy
make demo-tn-subset
```

Expected: subset build succeeds, KB created, files uploaded, worker logs show the records flow completing and embeddings indexed.

- [ ] **Step 6: Final commit (only if any doc/spec polish was needed)**

```bash
git status
# If anything is uncommitted at this point, fix it.
```

---

## Plan Self-Review Notes

Items the implementer should verify when starting any task:

- The "natural_key" concept mentioned in the spec is implemented in this plan via the existing deterministic record-id synthesis (`"{entity_type}:{raw_id}"`) for the records flow, and via the optional `natural_keys` constructor argument on `LlmDocumentExtractor` for the document flow. We did **not** add a `natural_key` field to `EntityDefinition` because the existing dedup mechanisms cover the demo's needs — adding it would touch more files than necessary for the slice. If the LLM extractor's `natural_keys` argument is ever migrated into config, that work is a follow-up.
- The plan assumes per-feed mappers are config-driven (not Python). This was confirmed by reading `backend/records/mappers/feed_mapper.py` — all NPPES/DE-SynPUF work is YAML in Phase 3, not new Python classes.
- The plan assumes the existing `GraphService.delete_knowledge_base` and `VectorService.delete_knowledge_base` are correct — they were verified to exist in `backend/graph/service.py:300` and `backend/vectorstore/service.py:198`.
- Provenance metadata field names (`source_kind`, `source_document_id`, `source_chunk_id`, `source_feed`, `source_raw_record_id`) are used consistently across all tasks. Do not deviate from these names without updating every consumer.
