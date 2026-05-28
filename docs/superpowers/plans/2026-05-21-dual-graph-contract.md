# Dual-Graph Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mutate the read-side protocols on graph, vectorstore, and rag from `knowledge_base_id: str` to `knowledge_base_ids: list[str]`, add a `resolve_kb_scope` helper that expands a single primary KB id into the full read scope using a new `DomainConfig.default_reference_kb_id` field, and wire the resolver into the API handler boundary. Writes stay scalar. The change is wide but mechanical.

**Architecture:** A small pure resolver function (`shared/kb_scope.py`) is the single point of policy: it consults the loaded `DomainConfig` and a `KnowledgeBaseRepository` to expand a primary kb_id into `[primary]` or `[primary, reference]`. API read endpoints call the resolver once and pass the resulting list to services. Protocols, services, adapters, and request/response models on the read path all change uniformly from scalar to list. Writes — including `update_entity_properties`, `delete_knowledge_base`, `upsert_task`, `VectorIndexRequest`, `query_neighborhood`, `compute_metrics` — stay scalar by design.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Neo4j 5 Cypher driver, Qdrant Python client, pytest, pyright strict, ruff.

**Spec:** `docs/superpowers/specs/2026-05-21-dual-graph-contract-design.md`

---

## Conventions Used Throughout

- All paths are relative to repo root unless prefixed with `/`.
- Backend commands run from `backend/` with the host venv activated: `source /home/rdhagan92/chiliAI/backend/.venv/bin/activate` followed by the command.
- TDD discipline: each task that adds behavior writes the failing test first.
- The change cascades through the Python type system; once a protocol's parameter shape changes, every caller must be updated in the same commit (otherwise `pyright --strict` blocks). Tasks 3–5 are therefore single-commit module-wide changes by necessity.
- Parameter naming: use `knowledge_base_ids: list[str]` (consistent with existing `knowledge_base_id` naming convention).

---

## Task 1: Add `DomainConfig.default_reference_kb_id` field

Backwards-compatible field addition; no consumer touches the field yet. Stands alone.

**Files:**
- Modify: `backend/config/schema.py` (the `DomainConfig` class around line 341)
- Modify: `backend/tests/config/test_schema.py` (if it exists — verify and extend)

- [ ] **Step 1: Verify or locate the existing DomainConfig test file**

Run:

```bash
ls /home/rdhagan92/chiliAI/backend/tests/config/ 2>&1
```

If `test_schema.py` exists, extend it. If not, create it.

- [ ] **Step 2: Write the failing test**

Add to (or create) `backend/tests/config/test_schema.py`:

```python
from config.schema import DomainConfig


def _minimal_domain_config_kwargs() -> dict[str, object]:
    """Return the minimum kwargs needed to instantiate a DomainConfig."""
    return {
        "domain": {
            "name": "test_domain",
            "display_name": "Test Domain",
            "description": "Test domain for unit tests.",
        },
    }


def test_domain_config_default_reference_kb_id_is_none_by_default() -> None:
    config = DomainConfig(**_minimal_domain_config_kwargs())
    assert config.default_reference_kb_id is None


def test_domain_config_default_reference_kb_id_accepts_string() -> None:
    config = DomainConfig(
        **_minimal_domain_config_kwargs(),
        default_reference_kb_id="kb-policy-v1",
    )
    assert config.default_reference_kb_id == "kb-policy-v1"
```

**Important:** Run the test before editing the schema to confirm the minimal-kwargs construction works on the current `DomainConfig` shape. If `DomainConfig` requires additional fields beyond `domain`, expand `_minimal_domain_config_kwargs` until the constructor succeeds for the `is_none_by_default` test under the OLD schema (without the new field). Then the second test (`accepts_string`) is the actual failing test.

- [ ] **Step 3: Run the tests to confirm the second test fails**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && source .venv/bin/activate && pytest tests/config/test_schema.py -v 2>&1 | tail -10
```

Expected: `test_domain_config_default_reference_kb_id_accepts_string` fails because the field doesn't exist yet (Pydantic v2 raises `ValidationError` on extra fields by default, OR the field is silently dropped — either way the assertion `config.default_reference_kb_id == "kb-policy-v1"` will fail).

- [ ] **Step 4: Add the field to `DomainConfig`**

In `backend/config/schema.py`, locate the `class DomainConfig(BaseModel):` definition (around line 341). Add the new field at the end of the class body, after the last existing field. Also ensure `from pydantic import Field` is already imported (it should be, since other classes in the file use it).

Add the field:

```python
    default_reference_kb_id: str | None = Field(
        default=None,
        description=(
            "ID of a knowledge base that is auto-attached to every read in this "
            "domain (the 'policy graph'). When None, dual-graph behavior is disabled "
            "and reads scope to the primary KB only."
        ),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/config/test_schema.py -v 2>&1 | tail -10
```

Expected: both tests pass.

- [ ] **Step 6: Run the full config test suite + pyright to confirm no regressions**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/config/ -v 2>&1 | tail -15 && pyright config/schema.py 2>&1 | tail -5
```

Expected: all config tests pass, pyright clean.

- [ ] **Step 7: Commit**

```bash
git add backend/config/schema.py backend/tests/config/test_schema.py
git commit -m "feat(config): add optional default_reference_kb_id to DomainConfig"
```

---

## Task 2: Create the `resolve_kb_scope` resolver

Pure-function helper with full test coverage. Has no consumer yet; the API layer will wire it up in Task 6.

**Files:**
- Create: `backend/shared/kb_scope.py`
- Create: `backend/tests/shared/test_kb_scope.py`

- [ ] **Step 1: Verify the `backend/shared/` test directory**

Run:

```bash
ls /home/rdhagan92/chiliAI/backend/tests/shared/ 2>&1
```

If the directory doesn't exist, the next step's file create will trigger its creation.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/shared/test_kb_scope.py`:

```python
"""Unit tests for the dual-graph scope resolver."""

import logging
from dataclasses import dataclass

import pytest

from config.schema import DomainConfig
from shared.kb_scope import resolve_kb_scope


def _minimal_domain_config(default_reference_kb_id: str | None = None) -> DomainConfig:
    return DomainConfig(
        domain={
            "name": "test_domain",
            "display_name": "Test Domain",
            "description": "Test domain.",
        },
        default_reference_kb_id=default_reference_kb_id,
    )


@dataclass
class _StubKbRepository:
    """Minimal KnowledgeBaseExistenceCheck stub."""

    existing_ids: set[str]

    def get(self, knowledge_base_id: str) -> object | None:
        return object() if knowledge_base_id in self.existing_ids else None


def test_returns_primary_only_when_no_reference_configured() -> None:
    config = _minimal_domain_config(default_reference_kb_id=None)
    repo = _StubKbRepository(existing_ids={"kb-claims"})

    scope = resolve_kb_scope("kb-claims", config, repo)

    assert scope == ["kb-claims"]


def test_returns_primary_and_reference_when_both_configured_and_exist() -> None:
    config = _minimal_domain_config(default_reference_kb_id="kb-policy")
    repo = _StubKbRepository(existing_ids={"kb-claims", "kb-policy"})

    scope = resolve_kb_scope("kb-claims", config, repo)

    assert scope == ["kb-claims", "kb-policy"]


def test_returns_primary_only_when_primary_is_the_reference() -> None:
    """No self-attach loop when the analyst queries the policy KB directly."""
    config = _minimal_domain_config(default_reference_kb_id="kb-policy")
    repo = _StubKbRepository(existing_ids={"kb-policy"})

    scope = resolve_kb_scope("kb-policy", config, repo)

    assert scope == ["kb-policy"]


def test_returns_primary_only_and_logs_warning_when_reference_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _minimal_domain_config(default_reference_kb_id="kb-missing")
    repo = _StubKbRepository(existing_ids={"kb-claims"})

    with caplog.at_level(logging.WARNING, logger="shared.kb_scope"):
        scope = resolve_kb_scope("kb-claims", config, repo)

    assert scope == ["kb-claims"]
    warning_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelname == "WARNING"
        and record.name == "shared.kb_scope"
    ]
    assert len(warning_messages) == 1
    assert "kb-missing" in warning_messages[0]
    assert "kb-claims" in warning_messages[0]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && source .venv/bin/activate && pytest tests/shared/test_kb_scope.py -v 2>&1 | tail -15
```

Expected: ImportError because `shared.kb_scope` doesn't exist yet.

- [ ] **Step 4: Create the resolver module**

Create `backend/shared/kb_scope.py`:

```python
"""Resolve a primary KB id into the full read scope for the domain.

The dual-graph contract allows reads to span a primary (transactional) KB
plus a domain-level reference (policy) KB. This module is the single point
of policy for assembling the read scope at the API handler boundary.
"""

from __future__ import annotations

import logging
from typing import Protocol

from config.schema import DomainConfig

logger = logging.getLogger(__name__)


class KnowledgeBaseExistenceCheck(Protocol):
    """Minimal protocol the resolver uses to verify a reference KB exists.

    The full `KnowledgeBaseRepository` (knowledgebases.protocols) satisfies this protocol
    because it has a `get(knowledge_base_id) -> KnowledgeBase | None` method.
    Tests can supply a smaller stub.
    """

    def get(self, knowledge_base_id: str) -> object | None: ...


def resolve_kb_scope(
    primary_kb_id: str,
    domain_config: DomainConfig,
    kb_repository: KnowledgeBaseExistenceCheck,
) -> list[str]:
    """Return the list of KB IDs that reads should span for this request.

    - If the domain has no ``default_reference_kb_id``, returns ``[primary]``.
    - If the primary IS the reference KB (the analyst is querying the policy
      KB itself), returns ``[primary]`` only — no self-attach loop.
    - If the reference KB is configured but doesn't exist, logs a WARNING and
      returns ``[primary]`` only. The app keeps running with degraded behavior.
    - Otherwise returns ``[primary, reference]`` in that order.

    Args:
        primary_kb_id: The active KB the analyst selected for the request.
        domain_config: The loaded domain configuration.
        kb_repository: An existence check against the KB metadata store.

    Returns:
        Ordered list of KB IDs that downstream protocols should read across.
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


__all__ = ["KnowledgeBaseExistenceCheck", "resolve_kb_scope"]
```

If the `backend/shared/` directory does not have an `__init__.py`, verify and create one:

```bash
ls /home/rdhagan92/chiliAI/backend/shared/__init__.py 2>&1
```

If missing, create an empty `backend/shared/__init__.py`. (This is unlikely — `shared.types` is imported from elsewhere — but verify.)

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/shared/test_kb_scope.py -v 2>&1 | tail -15
```

Expected: 4/4 tests pass.

- [ ] **Step 6: Pyright + ruff**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pyright shared/kb_scope.py tests/shared/test_kb_scope.py 2>&1 | tail -8 && ruff check shared/kb_scope.py tests/shared/test_kb_scope.py 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add backend/shared/kb_scope.py backend/tests/shared/test_kb_scope.py
git commit -m "feat(shared): add resolve_kb_scope for dual-graph read scope"
```

---

## Task 3: Migrate graph stack to multi-KB reads

This task changes `get_entity` and `search_entities` from `knowledge_base_id: str` to `knowledge_base_ids: list[str]` across:

- `backend/graph/protocols.py` (service protocol)
- `backend/graph/adapters/protocols.py` (repository protocol)
- `backend/graph/service.py` (service implementation)
- `backend/graph/adapters/in_memory.py` (in-memory repository)
- `backend/graph/adapters/neo4j_adapter.py` (Neo4j repository)
- `backend/tests/graph/*.py` (all test call sites)

`update_entity_properties`, `query_neighborhood`, `compute_metrics`, `delete_knowledge_base`, `upsert_task`, and `upsert_entities`/`upsert_relationships` (repository-level writes) stay scalar — they are writes or per-KB aggregates per the spec.

This is a single atomic commit by necessity: Python's type system enforces that protocol and call sites change together.

**Files:** (the six above plus any other test files that exercise the read methods)

- [ ] **Step 1: Write the failing test for `get_entity` multi-KB on the in-memory adapter**

In `backend/tests/graph/test_in_memory.py` (or wherever the in-memory tests live — verify with `ls backend/tests/graph/`), append a new test:

```python
def test_in_memory_get_entity_finds_entity_across_multiple_kb_ids() -> None:
    """get_entity with a multi-KB scope returns the match from whichever KB has it."""
    from graph.adapters.in_memory import InMemoryGraphRepository
    from shared.types import Entity

    repo = InMemoryGraphRepository()
    entity = Entity(id="entity-1", type="claim", properties={"x": 1})
    with repo.transaction("kb-claims"):
        repo.upsert_entities("kb-claims", [entity])

    # Search a scope that includes both an empty KB and the populated one.
    result = repo.get_entity(["kb-other-empty", "kb-claims"], "entity-1")

    assert result is not None
    assert result.id == "entity-1"


def test_in_memory_get_entity_returns_none_when_no_kb_in_scope_has_it() -> None:
    from graph.adapters.in_memory import InMemoryGraphRepository

    repo = InMemoryGraphRepository()
    result = repo.get_entity(["kb-a", "kb-b"], "entity-missing")
    assert result is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && source .venv/bin/activate && pytest tests/graph/test_in_memory.py::test_in_memory_get_entity_finds_entity_across_multiple_kb_ids -v 2>&1 | tail -10
```

Expected: FAIL — `get_entity` currently takes `knowledge_base_id: str`, not a list.

- [ ] **Step 3: Update `GraphRepository` protocol in `backend/graph/adapters/protocols.py`**

Locate the repository protocol (verify exact location with `grep -n "def get_entity" backend/graph/adapters/protocols.py`). Change ONLY these two methods from scalar to list:

```python
    def get_entity(
        self,
        knowledge_base_ids: list[str],
        entity_id: str,
    ) -> Entity | None: ...

    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]: ...
```

Leave every other method (transaction, upsert_entities, upsert_relationships, get_entities, get_relationships, get_neighbors, update_entity_properties, delete_knowledge_base, compute_metrics) with its existing scalar `knowledge_base_id: str` signature.

**Note:** if `get_neighbors` or `compute_metrics` are not in the repository protocol but only in the service protocol, that's fine — the spec puts them at the service level and they stay scalar at both.

- [ ] **Step 4: Update `GraphServiceProtocol` in `backend/graph/protocols.py`**

Replace the two affected method signatures:

```python
    def get_entity(
        self,
        knowledge_base_ids: list[str],
        entity_id: str,
    ) -> Entity | None: ...

    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]: ...
```

Every other method on `GraphServiceProtocol` is unchanged.

- [ ] **Step 5: Update `InMemoryGraphRepository` (`backend/graph/adapters/in_memory.py`)**

Replace the `get_entity` and `search_entities` method bodies. Locate them with:

```bash
grep -n "def get_entity\|def search_entities" backend/graph/adapters/in_memory.py
```

Replace `get_entity`:

```python
    def get_entity(
        self,
        knowledge_base_ids: list[str],
        entity_id: str,
    ) -> Entity | None:
        for kb_id in knowledge_base_ids:
            entity = self._entities.get(kb_id, {}).get(entity_id)
            if entity is not None:
                return entity
        return None
```

Replace `search_entities` (find the existing body first to preserve its filter/scoring logic). The pattern is: iterate over `knowledge_base_ids`, run the existing single-KB logic for each, concatenate results, sort by relevance/id, slice with limit+offset. Update accordingly while preserving the existing matching algorithm.

If the existing implementation is something like:

```python
    def search_entities(
        self,
        knowledge_base_id: str,
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        bucket = self._entities.get(knowledge_base_id, {})
        candidates = [...]  # existing match/filter logic
        return candidates[offset:offset + limit]
```

Replace with:

```python
    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        all_candidates: list[Entity] = []
        for kb_id in knowledge_base_ids:
            bucket = self._entities.get(kb_id, {})
            # ... existing match/filter logic from the old single-KB body ...
            all_candidates.extend(candidates_for_this_kb)
        # Sort/dedupe if the existing logic required it, then slice.
        return all_candidates[offset:offset + limit]
```

Read the existing implementation carefully and preserve its semantics — only the iteration scope changes.

- [ ] **Step 6: Update `Neo4jGraphRepository` (`backend/graph/adapters/neo4j_adapter.py`)**

Locate the two methods:

```bash
grep -n "def get_entity\|def search_entities" backend/graph/adapters/neo4j_adapter.py
```

For `get_entity`, change the Cypher from `{knowledge_base_id: $knowledge_base_id, entity_id: $entity_id}` map-match to a WHERE-IN match, and update the method signature:

```python
    def get_entity(
        self,
        knowledge_base_ids: list[str],
        entity_id: str,
    ) -> Entity | None:
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{entity_id: $entity_id}})
        WHERE entity.knowledge_base_id IN $knowledge_base_ids
        RETURN entity
        LIMIT 1
        """
        entities = self._query_entities(
            query,
            knowledge_base_ids=knowledge_base_ids,
            entity_id=entity_id,
        )
        return entities[0] if entities else None
```

For `search_entities`, apply the same `WHERE knowledge_base_id IN $knowledge_base_ids` transformation. Find the existing query (it likely already uses the map-match form on `{knowledge_base_id: $knowledge_base_id, ...}`) and change it to the WHERE-IN form. Update the method signature.

The composite index `(:Entity {knowledge_base_id, entity_id})` covers `WHERE knowledge_base_id IN [...]` efficiently per the leading-column principle (verified by the schema-index work that landed in commit `21d43b7`).

- [ ] **Step 7: Update `GraphService` in `backend/graph/service.py`**

Locate `get_entity` and `search_entities` on the service:

```bash
grep -n "def get_entity\|def search_entities" backend/graph/service.py
```

Update both to take `knowledge_base_ids: list[str]` and pass through to the repository:

```python
    def get_entity(
        self,
        knowledge_base_ids: list[str],
        entity_id: str,
    ) -> Entity | None:
        return self._repository.get_entity(knowledge_base_ids, entity_id)

    def search_entities(
        self,
        knowledge_base_ids: list[str],
        query: str,
        limit: int,
        offset: int,
    ) -> list[Entity]:
        return self._repository.search_entities(
            knowledge_base_ids, query, limit, offset
        )
```

Every other service method (upsert_task, update_entity_properties, query_neighborhood, compute_metrics, delete_knowledge_base) is unchanged.

- [ ] **Step 8: Find and fix every test call site**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && grep -rn "get_entity\|search_entities" tests/graph/ | head -30
```

Every call to `get_entity(kb_id, entity_id)` becomes `get_entity([kb_id], entity_id)`. Same for `search_entities`. Wrap the existing scalar argument in a single-element list. Tests that previously asserted "this fetches from one KB" still pass because `[kb_id]` is a single-KB scope.

Do NOT touch calls to `get_neighbors`, `update_entity_properties`, `upsert_entities`, `upsert_relationships`, `compute_metrics`, `delete_knowledge_base` — those stay scalar.

- [ ] **Step 9: Also check API handler call sites that pass `kb_id` directly**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && grep -rn "\.get_entity(\|\.search_entities(" --include="*.py" | grep -v tests/ | head -20
```

For each API handler that calls these methods on the service: temporarily wrap the existing `kb_id` argument in `[kb_id]`. Task 6 will replace this temporary wrapping with the real `resolve_kb_scope(kb_id, ...)` call. The point is that the type system stays consistent through this task.

- [ ] **Step 10: Run the full graph test suite**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/graph/ -v 2>&1 | tail -20
```

Expected: all tests pass (including the two new in-memory multi-KB tests). The 2 Neo4j integration tests stay skipped without the optional dep.

- [ ] **Step 11: Add a Neo4j integration test for multi-KB get_entity (optional — skipped unless `[neo4j]` extra is installed)**

In `backend/tests/graph/test_neo4j_adapter.py`, add a new test guarded by the existing integration marker pattern. Find the existing integration tests with:

```bash
grep -n "pytest.mark.integration\|@pytest.mark.integration" backend/tests/graph/test_neo4j_adapter.py | head -5
```

Add a new integration test that:
1. Upserts an entity to `kb-a`
2. Upserts a different entity to `kb-b`
3. Calls `get_entity(["kb-a", "kb-b"], "entity-from-a")` and asserts it returns the kb-a entity
4. Calls `get_entity(["kb-c"], "entity-from-a")` and asserts None

Skip this step if the existing test file has zero integration tests (then there's no established pattern; defer to a follow-up).

- [ ] **Step 12: Pyright + ruff**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pyright graph/ 2>&1 | tail -10 && ruff check graph/ tests/graph/ 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 13: Commit**

```bash
git add backend/graph/protocols.py backend/graph/adapters/protocols.py backend/graph/service.py backend/graph/adapters/in_memory.py backend/graph/adapters/neo4j_adapter.py backend/tests/graph/
git commit -m "feat(graph): accept list[str] kb_ids on read methods for dual-graph"
```

---

## Task 4: Migrate vectorstore stack to multi-KB reads

`VectorSearchRequest.knowledge_base_id` and `VectorSearchResponse.knowledge_base_id` change from `str` to `knowledge_base_ids: list[str]`. The protocol `search(request)` method signature does not change (it accepts a request object), but the request shape changes, which cascades.

`VectorIndexRequest`, `VectorIndexReceipt`, and the `index` method stay scalar — these are writes.

**Files:**
- Modify: `backend/vectorstore/service_models.py`
- Modify: `backend/vectorstore/service.py`
- Modify: `backend/vectorstore/adapters/in_memory.py`
- Modify: `backend/vectorstore/adapters/qdrant_adapter.py`
- Modify: `backend/vectorstore/adapters/protocols.py` (if it has its own copy of the request types)
- Modify: `backend/tests/vectorstore/` (all relevant test files)

- [ ] **Step 1: Write the failing test**

In `backend/tests/vectorstore/test_in_memory.py` (verify the actual filename with `ls backend/tests/vectorstore/`), append:

```python
def test_in_memory_vector_search_spans_multiple_kb_ids() -> None:
    from vectorstore.adapters.in_memory import InMemoryVectorRepository
    from vectorstore.service_models import (
        VectorIndexRequest,
        VectorIndexSubmission,
        VectorSearchRequest,
    )

    repo = InMemoryVectorRepository()

    # Index into two separate KBs.
    repo.index(VectorIndexRequest(
        knowledge_base_id="kb-a",
        submissions=[
            VectorIndexSubmission(
                record_id="rec-a-1",
                content_id="content-a-1",
                embedding=[1.0, 0.0, 0.0],
                metadata={},
            ),
        ],
    ))
    repo.index(VectorIndexRequest(
        knowledge_base_id="kb-b",
        submissions=[
            VectorIndexSubmission(
                record_id="rec-b-1",
                content_id="content-b-1",
                embedding=[1.0, 0.0, 0.0],
                metadata={},
            ),
        ],
    ))

    response = repo.search(VectorSearchRequest(
        knowledge_base_ids=["kb-a", "kb-b"],
        query_vector=[1.0, 0.0, 0.0],
        limit=10,
    ))

    record_ids = {match.record_id for match in response.matches}
    assert record_ids == {"rec-a-1", "rec-b-1"}
    assert response.knowledge_base_ids == ["kb-a", "kb-b"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/vectorstore/ -k "test_in_memory_vector_search_spans_multiple_kb_ids" -v 2>&1 | tail -10
```

Expected: FAIL — `VectorSearchRequest` and `VectorSearchResponse` don't have `knowledge_base_ids` yet.

- [ ] **Step 3: Update `VectorSearchRequest` and `VectorSearchResponse`**

In `backend/vectorstore/service_models.py`, find the two models:

```bash
grep -n "class VectorSearchRequest\|class VectorSearchResponse" backend/vectorstore/service_models.py
```

For `VectorSearchRequest` (currently around line 63), replace `knowledge_base_id: str` with `knowledge_base_ids: list[str]`. The full updated class (preserving the existing query_vector / limit / filters / validators):

```python
class VectorSearchRequest(BaseModel):
    """A vector similarity-search request."""

    knowledge_base_ids: list[str] = Field(min_length=1)
    query_vector: list[float] = Field(default_factory=_empty_embedding)
    limit: int = Field(default=5, gt=0)
    filters: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_query(self) -> VectorSearchRequest:
        if not self.query_vector:
            raise ValueError("VectorSearchRequest requires a non-empty query_vector.")
        return self
```

For `VectorSearchResponse` (currently around line 88), replace `knowledge_base_id: str` with `knowledge_base_ids: list[str]`:

```python
class VectorSearchResponse(BaseModel):
    """Response returned by a vector similarity-search request."""

    knowledge_base_ids: list[str] = Field(min_length=1)
    query_dimension: int = Field(gt=0)
    matches: list[VectorSearchMatch] = Field(default_factory=_empty_matches)
```

Leave `VectorIndexRequest` (line 40) and `VectorIndexReceipt` (line 53) unchanged — these are write models.

- [ ] **Step 4: Update `InMemoryVectorRepository.search`**

In `backend/vectorstore/adapters/in_memory.py`, locate the `search` method:

```bash
grep -n "def search" backend/vectorstore/adapters/in_memory.py
```

Read the existing implementation. It likely scopes by `request.knowledge_base_id`. Update to iterate over `request.knowledge_base_ids`, concatenate matches across KBs, sort by score, slice by limit. The response now carries `knowledge_base_ids=request.knowledge_base_ids`.

If the existing logic is roughly:

```python
def search(self, request: VectorSearchRequest) -> VectorSearchResponse:
    bucket = self._records.get(request.knowledge_base_id, {})
    matches = self._score_matches(bucket, request.query_vector, request.limit, request.filters)
    return VectorSearchResponse(
        knowledge_base_id=request.knowledge_base_id,
        query_dimension=len(request.query_vector),
        matches=matches,
    )
```

Replace with:

```python
def search(self, request: VectorSearchRequest) -> VectorSearchResponse:
    all_matches: list[VectorSearchMatch] = []
    for kb_id in request.knowledge_base_ids:
        bucket = self._records.get(kb_id, {})
        all_matches.extend(self._score_matches(bucket, request.query_vector, request.limit * len(request.knowledge_base_ids), request.filters))
    # Sort by score descending and take top `limit`.
    all_matches.sort(key=lambda m: m.score, reverse=True)
    top_matches = all_matches[:request.limit]
    return VectorSearchResponse(
        knowledge_base_ids=request.knowledge_base_ids,
        query_dimension=len(request.query_vector),
        matches=top_matches,
    )
```

The `limit * len(...)` over-fetch ensures we still get the top N across KBs after concatenation. Tune to match the existing implementation's semantics if it differs.

- [ ] **Step 5: Update `QdrantVectorRepository.search`**

In `backend/vectorstore/adapters/qdrant_adapter.py`, locate the `search` method and its Qdrant filter construction. The filter currently uses something like:

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue
qdrant_filter = Filter(
    must=[FieldCondition(key="kb_id", match=MatchValue(value=request.knowledge_base_id))]
)
```

Replace with `MatchAny`:

```python
from qdrant_client.models import Filter, FieldCondition, MatchAny
qdrant_filter = Filter(
    must=[FieldCondition(key="kb_id", match=MatchAny(any=request.knowledge_base_ids))]
)
```

Update the response to use `knowledge_base_ids=request.knowledge_base_ids`.

Verify the import path for `MatchAny` against the installed `qdrant_client` version — the exact symbol path may need adjustment. If `MatchAny` is not exported in the expected location, search the installed package for the correct symbol.

- [ ] **Step 6: Update `VectorService.search` (if it does any non-passthrough work)**

In `backend/vectorstore/service.py`, locate `search`. Typically the service is a thin pass-through to the repository: `return self._repository.search(request)`. If it does anything more, ensure it propagates `knowledge_base_ids` correctly through any internal state.

- [ ] **Step 7: Update all vectorstore test call sites**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && grep -rn "VectorSearchRequest(\|VectorSearchResponse(" tests/vectorstore/ | head -30
```

Every `VectorSearchRequest(knowledge_base_id="kb-x", ...)` becomes `VectorSearchRequest(knowledge_base_ids=["kb-x"], ...)`. Same for response constructions in assertions.

Index-side constructions (`VectorIndexRequest(knowledge_base_id="kb-x", ...)`) are unchanged.

- [ ] **Step 8: Also update API handlers / call sites that construct `VectorSearchRequest`**

```bash
cd /home/rdhagan92/chiliAI/backend && grep -rn "VectorSearchRequest(" --include="*.py" | grep -v tests/ | head -10
```

For each non-test construction: wrap the existing single `kb_id` in `[kb_id]` for now. Task 6 replaces these with `resolve_kb_scope` results.

- [ ] **Step 9: Run the full vectorstore test suite**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/vectorstore/ -v 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 10: Pyright + ruff**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pyright vectorstore/ 2>&1 | tail -10 && ruff check vectorstore/ tests/vectorstore/ 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 11: Commit**

```bash
git add backend/vectorstore/ backend/tests/vectorstore/
git commit -m "feat(vectorstore): accept list[str] knowledge_base_ids on search for dual-graph"
```

---

## Task 5: Migrate RAG stack to multi-KB reads

`RagQueryRequest.knowledge_base_id` and `RagQueryResponse.knowledge_base_id` change to `knowledge_base_ids: list[str]`. `RagServiceProtocol.answer_question(*, knowledge_base_id: str, ...)` becomes `knowledge_base_ids: list[str]`.

**Files:**
- Modify: `backend/rag/protocols.py`
- Modify: `backend/rag/service_models.py`
- Modify: `backend/rag/service.py`
- Modify: `backend/tests/rag/`

- [ ] **Step 1: Write the failing test**

In `backend/tests/rag/test_service.py` (verify location with `ls backend/tests/rag/`), append:

```python
def test_rag_service_answer_question_accepts_list_of_kb_ids() -> None:
    """answer_question takes knowledge_base_ids: list[str] post-dual-graph."""
    # Use the existing RagService construction helper / fixture for this test module.
    # See existing tests in the file for the construction pattern.
    service = _build_minimal_rag_service()  # uses existing helper or fixture

    answer = service.answer_question(
        knowledge_base_ids=["kb-claims", "kb-policy"],
        question="What providers are excluded?",
    )

    assert answer.knowledge_base_ids == ["kb-claims", "kb-policy"]
```

Adapt `_build_minimal_rag_service` to whatever fixture pattern already exists in `test_service.py`. If the existing tests use module-level fixtures, mirror that pattern.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/rag/test_service.py::test_rag_service_answer_question_accepts_list_of_kb_ids -v 2>&1 | tail -10
```

Expected: FAIL — `answer_question` doesn't accept `knowledge_base_ids` yet.

- [ ] **Step 3: Update `RagQueryRequest` and `RagQueryResponse`**

In `backend/rag/service_models.py`, find the two models (around lines 25 and 55 based on earlier grep). Replace `knowledge_base_id: str` with `knowledge_base_ids: list[str] = Field(min_length=1)` in both.

The exact text changes (read the existing models first, then apply the rename in place):

```python
# RagQueryRequest
class RagQueryRequest(BaseModel):
    knowledge_base_ids: list[str] = Field(min_length=1)
    # ... rest unchanged ...

# RagQueryResponse
class RagQueryResponse(BaseModel):
    knowledge_base_ids: list[str] = Field(min_length=1)
    # ... rest unchanged ...
```

If `RagAnswer` (used by `answer_question`) has its own `knowledge_base_id` field, rename to `knowledge_base_ids: list[str]` as well. Confirm with:

```bash
grep -n "knowledge_base_id" backend/rag/service_models.py
```

- [ ] **Step 4: Update `RagServiceProtocol.answer_question` signature**

In `backend/rag/protocols.py`:

```python
    def answer_question(
        self,
        *,
        knowledge_base_ids: list[str],
        question: str,
    ) -> RagAnswer: ...
```

- [ ] **Step 5: Update `RagService` implementation**

In `backend/rag/service.py`, locate the `answer_question` method and the `answer`/`stream_answer` methods. Replace every internal `knowledge_base_id` plumbing with `knowledge_base_ids`. The internal state shape (`state.knowledge_base_id` per the earlier grep) and any helper methods need the same rename.

This is the most invasive single-file edit in the entire plan. Read the existing file end-to-end before editing:

```bash
cat backend/rag/service.py | head -250
```

Make the renames consistently. The RAG service forwards the list through to vector and graph services, both of which now accept lists (Tasks 4 and 3). So every internal use of `knowledge_base_id` should become `knowledge_base_ids` and pass straight through. If the RAG service uses `VectorSearchRequest(knowledge_base_id=...)`, update it to `VectorSearchRequest(knowledge_base_ids=request.knowledge_base_ids, ...)`. If it calls `graph_service.search_entities(kb_id, ...)`, update to `graph_service.search_entities(request.knowledge_base_ids, ...)`.

If you find a true single-KB consumer that can't take a list (e.g., a metric helper that returns per-KB stats), STOP and escalate to the controller — this would mean the spec missed a write-vs-read classification. Do not silently take `knowledge_base_ids[0]` to work around it.

- [ ] **Step 6: Update RAG test call sites**

```bash
cd /home/rdhagan92/chiliAI/backend && grep -rn "RagQueryRequest(\|answer_question(\|RagQueryResponse(" tests/rag/ | head -20
```

Every construction with `knowledge_base_id="kb-x"` becomes `knowledge_base_ids=["kb-x"]`. Every keyword call `answer_question(knowledge_base_id="kb-x", question=...)` becomes `answer_question(knowledge_base_ids=["kb-x"], question=...)`.

- [ ] **Step 7: Update API handler call sites that construct these models**

```bash
cd /home/rdhagan92/chiliAI/backend && grep -rn "RagQueryRequest(\|answer_question(" --include="*.py" | grep -v tests/ | head -10
```

Wrap each existing scalar `kb_id` in `[kb_id]` for now. Task 6 replaces with `resolve_kb_scope`.

- [ ] **Step 8: Run the full RAG test suite**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/rag/ -v 2>&1 | tail -25
```

Expected: all tests pass.

- [ ] **Step 9: Pyright + ruff**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pyright rag/ 2>&1 | tail -10 && ruff check rag/ tests/rag/ 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 10: Commit**

```bash
git add backend/rag/ backend/tests/rag/
git commit -m "feat(rag): accept list[str] knowledge_base_ids on retrieval requests for dual-graph"
```

---

## Task 6: Wire `resolve_kb_scope` into API read handlers

Replace the `[kb_id]` temporary wrappers (from Tasks 3–5) with real `resolve_kb_scope(kb_id, domain_config, kb_repository)` calls at each affected API read endpoint.

**Files:**
- Modify: API router files that call the affected service methods. Likely candidates:
  - `backend/api/routers/investigation.py`
  - `backend/api/routers/rag.py`
  - Any others — discover via the temp-wrapper grep below.
- Modify: `backend/api/dependencies.py` if a `Depends(get_domain_config)` provider isn't already there (very likely it IS — verify).
- Modify: `backend/tests/api/` corresponding test files.

- [ ] **Step 1: Find every temporary `[kb_id]` wrapper introduced in Tasks 3–5**

```bash
cd /home/rdhagan92/chiliAI/backend && grep -rn "\.get_entity(\[\|\.search_entities(\[\|VectorSearchRequest(\s*knowledge_base_ids=\[\|RagQueryRequest(\s*knowledge_base_ids=\[\|answer_question(\s*knowledge_base_ids=\[" --include="*.py" | grep -v tests/
```

Each of these is a temporary wrapper that needs to be replaced with `resolve_kb_scope(kb_id, domain_config, kb_repository)`.

- [ ] **Step 2: Confirm the `get_domain_config` and `get_knowledge_base_repository` dependency providers exist**

```bash
grep -n "get_domain_config\|get_knowledge_base_repository" backend/api/dependencies.py
```

Both should exist (the existing API already uses both). If `get_domain_config` doesn't exist, add a thin provider that returns the loaded `DomainConfig`. The config is typically loaded once at app startup; the provider returns the cached instance.

- [ ] **Step 3: For each affected endpoint, add the dependencies and call the resolver**

Pattern (apply to each endpoint that uses one of the temp-wrapped service methods):

```python
from shared.kb_scope import resolve_kb_scope

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
    # ... existing response shaping unchanged ...
```

Apply the same shape to every endpoint that calls:
- `graph_service.get_entity(...)`
- `graph_service.search_entities(...)`
- `vector_service.search(VectorSearchRequest(knowledge_base_ids=..., ...))`
- `rag_service.answer_question(knowledge_base_ids=..., ...)`
- `rag_service.answer(RagQueryRequest(knowledge_base_ids=..., ...))`

Endpoints that call `graph_service.query_neighborhood`, `graph_service.compute_metrics`, `graph_service.update_entity_properties`, `graph_service.delete_knowledge_base`, or `vector_service.index` need NO changes — they stay scalar.

- [ ] **Step 4: Write an integration-style test for one end-to-end read with auto-attach configured**

In `backend/tests/api/test_investigation.py` (or wherever the existing investigation API tests live), add a test that:

1. Loads a `DomainConfig` with `default_reference_kb_id="kb-policy"` set.
2. Seeds two KBs in the test KB repository: `kb-claims` (with entity `entity-1`) and `kb-policy` (with entity `entity-2`).
3. Calls `GET /investigation/{kb-claims}/entities/entity-2`.
4. Asserts the response is the entity-2 from kb-policy (not 404), proving the auto-attach worked.

If the existing test pattern uses a TestClient with deps overridden, mirror it. If you can't find the right test file, add a new one named `test_dual_graph_auto_attach.py` in `backend/tests/api/`.

- [ ] **Step 5: Run the API test suite**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest tests/api/ -v 2>&1 | tail -25
```

Expected: all tests pass including the new dual-graph integration test.

- [ ] **Step 6: Pyright + ruff**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pyright api/ 2>&1 | tail -10 && ruff check api/ tests/api/ 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add backend/api/ backend/tests/api/
git commit -m "feat(api): expand kb scope via resolve_kb_scope at read endpoints"
```

---

## Task 7: Update documentation

**Files:**
- Modify: `backend/graph/README.md`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Update `backend/graph/README.md`**

Append a new section after the existing "Neo4j Schema Invariants" section:

```markdown
## Dual-Graph Reads

Read-side methods on `GraphServiceProtocol` (`get_entity`, `search_entities`) accept `knowledge_base_ids: list[str]` and span all listed KBs. The API handler boundary uses `shared.kb_scope.resolve_kb_scope(primary, domain_config, kb_repo)` to expand a single primary KB id into the full read scope, auto-attaching the domain's `default_reference_kb_id` (the "policy graph") when configured.

Write methods (`upsert_task`, `update_entity_properties`, `delete_knowledge_base`) and the neighborhood traversal (`query_neighborhood`) and metrics aggregation (`compute_metrics`) stay scoped to a single KB. Cross-KB joining of distinct entities (e.g., a provider node in claims-KB and the same NPI in policy-KB) is the consumer's responsibility (RAG context builder, UI presentation), not the graph adapter's.
```

- [ ] **Step 2: Update `docs/architecture.md`**

Find the section that discusses graph storage or knowledge bases (grep for "knowledge base" or "Neo4j" headings):

```bash
grep -n "^##\|knowledge base\|Neo4j" docs/architecture.md | head -20
```

Append a short paragraph at the end of the most relevant section (probably a "Knowledge Bases" or "Graph Storage" section), or as a new subsection if no good home exists:

```markdown
### Dual-Graph Reads

The platform supports a dual-graph model: a domain-level reference ("policy") KB containing slow-changing reference data (codesets, exclusion lists, policy documents) plus per-cycle transactional ("claims") KBs. Reads on the graph, vector store, and RAG layers span both via `knowledge_base_ids: list[str]` on the protocol surface. The API handler boundary resolves the primary KB into the full scope using `shared.kb_scope.resolve_kb_scope`, which honors the domain's `default_reference_kb_id`. Writes remain single-KB. Cross-KB property joining (e.g., matching providers by NPI across graphs) is deferred to consumer layers.
```

- [ ] **Step 3: Commit**

```bash
git add backend/graph/README.md docs/architecture.md
git commit -m "docs(graph): document dual-graph read scope across graph, vector, and rag"
```

---

## Task 8: Full verification

- [ ] **Step 1: Pyright strict**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && source .venv/bin/activate && pyright 2>&1 | tail -15
```

Expected: 0 errors.

- [ ] **Step 2: Ruff lint**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && ruff check . 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Full pytest with coverage**

Run:

```bash
cd /home/rdhagan92/chiliAI/backend && pytest --cov 2>&1 | tail -30
```

Expected: all tests pass, coverage ≥ 85% on every package touched (`graph`, `vectorstore`, `rag`, `api`, `shared`, `config`).

- [ ] **Step 4: Manual end-to-end smoke against the running dev stack**

The dev stack should already be running. If not, `cd /home/rdhagan92/chiliAI && make dev`.

After Task 8 Steps 1-3 pass, do the following manual checks (the controller will execute these directly — implementer subagents skip this step):

1. Restart the API to pick up the schema changes if needed: `docker compose -f docker-compose.dev.yaml restart chili-api`.
2. With NO `default_reference_kb_id` set in the loaded domain config, hit `GET /api/knowledgebases` and `GET /api/investigation/{kb-1}/entities/{some-entity-id}` (use a real entity id if seeded). Assert behavior is identical to pre-feature.
3. Add `default_reference_kb_id: kb-policy-test` to the loaded domain config, restart API. Hit the same endpoints. Confirm the WARNING is logged (because kb-policy-test doesn't exist yet) and the behavior is identical to step 2 (degraded fallback to primary-only scope).
4. Create a new KB via the UI or API with id `kb-policy-test`, then restart API. Hit an investigation endpoint and confirm entities from both kb-1 and kb-policy-test are returned for a search query that matches in both.

- [ ] **Step 5: No commit needed if Steps 1-3 all pass**

If anything fails in Steps 1-3, report precisely and let the controller decide next steps. Do not silently fix issues that surface here.

---

## Out of Scope (Tracked, Not Implemented)

- Creating, ingesting, or populating a policy KB (separate feature).
- Reference-data feed configs (NPI directory, OIG LEIE, CPT/HCPCS codesets).
- Cross-KB property joining at the adapter level. Distinct entities returned; consumer deduplicates.
- Multi-reference support (more than one reference KB per domain) — single-field shape is intentional.
- Per-request opt-out (e.g. `include_reference=false` query param).
- UI changes to surface the dual-graph behavior — the analyst doesn't see the reference KB in the picker.
- Per-KB capabilities (e.g. "this is a policy KB; disable certain features for it") — KB metadata stays as-is.

## Success Criteria (from spec)

- A domain config with `default_reference_kb_id: null` (or absent) produces identical behavior to pre-feature: reads scope to `[primary]`, no warnings, no regressions.
- Setting `default_reference_kb_id: "<existing-kb-id>"` causes graph reads, vector search, and RAG retrieval to span both KBs.
- Setting `default_reference_kb_id: "<missing-kb-id>"` logs a WARNING per request and degrades to primary-only scope without 4xx/5xx.
- Writes are unaffected (`update_entity_properties`, `delete_knowledge_base`, `upsert_task`, `VectorIndexRequest`, KB management endpoints behave identically).
- `query_neighborhood` and `compute_metrics` stay single-KB.
- `pyright --strict` clean, `ruff` clean, `pytest --cov` ≥ 85% in every touched package.
