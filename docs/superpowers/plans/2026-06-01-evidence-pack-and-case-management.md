# Evidence-Pack Vertical & Case Management v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the alert→evidence→case vertical — real graph-extracted evidence packs (BL-005), durable KB-scoped cases with promote-from-alert (BL-010), and the evidence-pack viewer UI (BL-006).

**Architecture:** Add `graph.get_subgraph` as the traversal primitive; the worker builds a real `ExplanationContext` (subgraph + risk + metrics) → `ExplainabilityService.generate` → persist to an object-store `EvidencePackRepository`; the API reads packs from that repo (de-seeding `ApiState`). A new `backend/cases/` module (in-memory + Postgres adapters + migration) backs KB-scoped CRUD and `POST /cases/promote`. Frontend gains an `EvidencePackViewer` (subgraph via `GraphCanvas`) and finishes the cases page.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 / psycopg (via `database.ConnectionProvider`) / Alembic · React 19 / TS strict / Vite / react-query / Playwright. Backend tests: pytest (host `backend/.venv`). Quality: `pyright --strict`, ≥85% coverage, ruff, ESLint.

**Spec:** [docs/superpowers/specs/2026-06-01-evidence-pack-and-case-management-design.md](../specs/2026-06-01-evidence-pack-and-case-management-design.md)

**Conventions for every task:** run backend tools via the host venv (`backend/.venv/bin/python -m pytest ...`, `backend/.venv/bin/pyright`, `backend/.venv/bin/ruff`). Avoid `@contextmanager`+`Iterator` (pyright-strict rejects it; use `AbstractContextManager`). After any change to a frontend-consumed Pydantic model: `python tools/export_openapi.py` → `cd chili_app && npm run codegen:api`.

---

## File Structure

**Phase A — graph foundation**
- Modify: `backend/graph/adapters/protocols.py` (add `get_subgraph`), `backend/graph/protocols.py` (service protocol + remove TODO), `backend/graph/service.py`, `backend/graph/adapters/in_memory.py`, `backend/graph/adapters/neo4j_adapter.py`
- Test: `backend/tests/graph/test_in_memory.py`, `backend/tests/graph/test_neo4j_adapter.py`

**Phase B — evidence repository + real extraction (BL-005)**
- Create: `backend/analytics/explainability/repository.py`, `backend/analytics/explainability/adapters/evidence_in_memory.py`, `backend/analytics/explainability/adapters/evidence_object_store.py`
- Modify: `backend/agent/coordinator.py` (real context source + persist), `backend/api/dependencies.py` (`get_evidence_pack_repository`), `backend/api/routers/evidence.py`, `backend/api/state.py` (remove evidence seeding)
- Test: `backend/tests/analytics/explainability/test_evidence_repository.py`, `backend/tests/agent/test_explainability_stage.py`, `backend/tests/api/test_evidence_router.py`

**Phase C — cases module (BL-010 backend)**
- Create: `backend/cases/__init__.py`, `models.py`, `exceptions.py`, `service.py`, `adapters/__init__.py`, `adapters/protocols.py`, `adapters/in_memory.py`, `adapters/postgres.py`, `backend/cases/README.md`
- Create: `backend/database/migrations/versions/0002_cases.py`
- Modify: `backend/api/dependencies.py` (`get_case_repository` + payload factories), `backend/api/routers/cases.py`, `backend/api/contracts.py`, `backend/api/state.py` (KB-scope `open_cases`/policy-gap, drop `_seed_cases` from prod path)
- Test: `backend/tests/cases/test_in_memory_store.py`, `backend/tests/cases/test_postgres_store.py`, `backend/tests/api/test_cases_router.py`, `backend/tests/api/test_case_repository_selection.py`

**Phase D — frontend (BL-006 + BL-010 finish)**
- Create: `chili_app/src/api/subgraph.ts`, `chili_app/src/components/investigation/EvidencePackViewer.tsx`, tests + e2e helper
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`, `AlertFeedPage.tsx`, `CaseManagementPage.tsx`, `chili_app/src/api/cases.ts`, contracts (regenerated)
- Test: `chili_app/src/components/investigation/__tests__/EvidencePackViewer.test.tsx`, page tests, `chili_app/e2e/*.spec.ts`

**Phase E — docs + backlog + verify**

---

## Phase A — `graph.get_subgraph`

### Task A1: Add `get_subgraph` to repository protocol

**Files:** Modify `backend/graph/adapters/protocols.py`

- [ ] **Step 1:** In `GraphRepository`, add the method signature next to `get_neighbors`, and remove any `get_subgraph` TODO comment:

```python
def get_subgraph(
    self,
    knowledge_base_id: str,
    seed_entity_ids: list[str],
    depth: int = 1,
) -> "SubgraphResult":
    """Return the deduplicated union of the depth-hop neighborhoods of every seed.

    Empty ``seed_entity_ids`` returns an empty SubgraphResult. Seeds absent from
    the graph are skipped. KB-scoped (REQ-GRAPH-002).
    """
    ...
```

- [ ] **Step 2:** Run `backend/.venv/bin/pyright backend/graph/adapters/protocols.py`. Expected: clean (protocol stub).
- [ ] **Step 3:** Commit: `git add backend/graph/adapters/protocols.py && git commit -m "feat(graph): add get_subgraph to repository protocol"`

### Task A2: In-memory multi-seed BFS (TDD)

**Files:** Test `backend/tests/graph/test_in_memory.py`; Modify `backend/graph/adapters/in_memory.py`

- [ ] **Step 1: Write failing tests.** Add to `test_in_memory.py` (adapt entity/relationship construction to the existing helpers in that file):

```python
def test_get_subgraph_unions_multiple_seed_neighborhoods(repo_with_chain):
    # graph: a-b-c-d (kb="kb1"); seeds a and d, depth 1
    result = repo_with_chain.get_subgraph("kb1", ["a", "d"], depth=1)
    assert {e.id for e in result.entities} == {"a", "b", "c", "d"}
    # relationships deduped, no duplicates when neighborhoods overlap
    assert len(result.relationships) == len({r.id for r in result.relationships})

def test_get_subgraph_empty_seeds_returns_empty(repo_with_chain):
    result = repo_with_chain.get_subgraph("kb1", [], depth=2)
    assert result.entities == [] and result.relationships == []

def test_get_subgraph_skips_unknown_seed(repo_with_chain):
    result = repo_with_chain.get_subgraph("kb1", ["a", "does-not-exist"], depth=1)
    assert "a" in {e.id for e in result.entities}

def test_get_subgraph_is_kb_scoped(repo_with_two_kbs):
    result = repo_with_two_kbs.get_subgraph("kb1", ["a"], depth=3)
    assert all(e.knowledge_base_id == "kb1" for e in result.entities)
```

- [ ] **Step 2:** Run `backend/.venv/bin/python -m pytest backend/tests/graph/test_in_memory.py -k get_subgraph -v`. Expected: FAIL (no `get_subgraph`).
- [ ] **Step 3: Implement** in `in_memory.py` by generalizing the existing single-seed BFS (currently `get_neighbors`, ~lines 84-139) to a shared helper that seeds the frontier with a set:

```python
def get_subgraph(self, knowledge_base_id, seed_entity_ids, depth=1):
    visited: set[str] = set()
    frontier = [sid for sid in seed_entity_ids if self._entity_exists(knowledge_base_id, sid)]
    rel_ids: set[str] = set()
    for _ in range(max(depth, 0) + 0):  # depth hops below
        pass
    # BFS: expand frontier `depth` times, collecting entities + traversed edges
    current = list(dict.fromkeys(frontier))
    visited.update(current)
    for _hop in range(depth):
        next_frontier: list[str] = []
        for node in current:
            for rel in self._adjacent_relationships(knowledge_base_id, node):
                rel_ids.add(rel.id)
                for other in (rel.source_id, rel.target_id):
                    if other not in visited:
                        visited.add(other); next_frontier.append(other)
        current = next_frontier
        if not current:
            break
    entities = [self._entities[(knowledge_base_id, eid)] for eid in visited
                if (knowledge_base_id, eid) in self._entities]
    relationships = [self._relationships[(knowledge_base_id, rid)] for rid in rel_ids
                     if (knowledge_base_id, rid) in self._relationships]
    return SubgraphResult(entities=entities, relationships=relationships)
```

(Use the adapter's actual internal index names/helpers — mirror what `get_neighbors` uses. Refactor the shared traversal into a private `_expand(kb, seeds, depth)` and have both `get_neighbors` and `get_subgraph` call it.)

- [ ] **Step 4:** Run the same pytest. Expected: PASS.
- [ ] **Step 5:** `backend/.venv/bin/pyright backend/graph/adapters/in_memory.py` clean; `backend/.venv/bin/ruff check backend/graph`.
- [ ] **Step 6:** Commit: `git add backend/graph/adapters/in_memory.py backend/tests/graph/test_in_memory.py && git commit -m "feat(graph): in-memory multi-seed get_subgraph"`

### Task A3: Service method

**Files:** Modify `backend/graph/protocols.py` (service protocol, remove TODO at ~:16-18), `backend/graph/service.py` (remove TODO at ~:29-31)

- [ ] **Step 1:** Add to `GraphServiceProtocol`: `def get_subgraph(self, knowledge_base_id: str, seed_entity_ids: list[str], depth: int = 1) -> SubgraphResult: ...`
- [ ] **Step 2:** Implement in `GraphService`: `return self._repository.get_subgraph(knowledge_base_id, seed_entity_ids, depth)`.
- [ ] **Step 3:** Add service test in `backend/tests/graph/test_service.py` (or existing service test file) asserting delegation. Run it: PASS.
- [ ] **Step 4:** `pyright` clean on `backend/graph/`. Commit: `feat(graph): GraphService.get_subgraph + remove get_subgraph TODOs`.

### Task A4: Neo4j adapter (TDD, integration-gated)

**Files:** Modify `backend/graph/adapters/neo4j_adapter.py`; Test `backend/tests/graph/test_neo4j_adapter.py`

- [ ] **Step 1:** Write an `@pytest.mark.integration` test mirroring A2 semantics against a live Neo4j (follow the existing integration test setup/teardown in that file; build a small chain, assert union + dedup + kb-scope + rollback safety).
- [ ] **Step 2:** Run `backend/.venv/bin/python -m pytest -m integration backend/tests/graph/test_neo4j_adapter.py -k get_subgraph -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `get_subgraph` using one parameterized Cypher routed through `_run_read`/active transaction. Validate `depth` as a positive int and interpolate as a literal (driver cannot parameterize `*0..n`):

```python
def get_subgraph(self, knowledge_base_id, seed_entity_ids, depth=1):
    if not seed_entity_ids:
        return SubgraphResult(entities=[], relationships=[])
    d = max(int(depth), 0)
    query = (
        "MATCH (s:Entity) WHERE s.kb_id = $kb AND s.id IN $seeds "
        f"MATCH p = (s)-[*0..{d}]-(n:Entity) WHERE n.kb_id = $kb "
        "WITH collect(DISTINCT n) AS ns, collect(DISTINCT relationships(p)) AS rels "
        "RETURN ns, rels"
    )
    rows = self._run_read(query, kb=knowledge_base_id, seeds=seed_entity_ids)
    # map rows -> Entity / Relationship via existing _record_to_entity / _record_to_relationship helpers, dedup by id
    ...
```

(Use the adapter's existing record-mapping helpers and node/relationship property names — match `get_neighbors`.)

- [ ] **Step 4:** If a live Neo4j is available (`make dev`), run the integration test: PASS. Otherwise note it as integration-gated and verify `pyright --strict backend/graph/adapters/neo4j_adapter.py` clean.
- [ ] **Step 5:** Commit: `feat(graph): neo4j get_subgraph (integration-gated)`.

---

## Phase B — Evidence repository + real extraction (BL-005)

### Task B1: `EvidencePackRepository` protocol + in-memory (TDD)

**Files:** Create `backend/analytics/explainability/repository.py`, `backend/analytics/explainability/adapters/evidence_in_memory.py`; Test `backend/tests/analytics/explainability/test_evidence_repository.py`

- [ ] **Step 1: Failing test:**

```python
from shared.types import EvidencePack
from analytics.explainability.adapters.evidence_in_memory import InMemoryEvidencePackRepository

def _pack(pid="ev-1", kb="kb1"):
    return EvidencePack(id=pid, alert_id="al-1", reasoning="r",
                        subgraph_nodes=["a"], subgraph_edges=[], confidence=0.8)

def test_put_then_get_roundtrip():
    repo = InMemoryEvidencePackRepository()
    repo.put("kb1", _pack())
    got = repo.get("kb1", "ev-1")
    assert got is not None and got.id == "ev-1"

def test_get_missing_returns_none():
    assert InMemoryEvidencePackRepository().get("kb1", "nope") is None

def test_kb_isolation():
    repo = InMemoryEvidencePackRepository(); repo.put("kb1", _pack())
    assert repo.get("kb2", "ev-1") is None

def test_delete_by_kb():
    repo = InMemoryEvidencePackRepository(); repo.put("kb1", _pack())
    assert repo.delete_by_kb("kb1") == 1 and repo.get("kb1", "ev-1") is None
```

- [ ] **Step 2:** Run pytest → FAIL.
- [ ] **Step 3:** Implement protocol (`repository.py`) and `InMemoryEvidencePackRepository` (dict keyed `(kb, id)`).
- [ ] **Step 4:** pytest PASS; pyright clean.
- [ ] **Step 5:** Commit: `feat(explainability): EvidencePackRepository protocol + in-memory adapter`.

### Task B2: Object-store adapter (TDD)

**Files:** Create `backend/analytics/explainability/adapters/evidence_object_store.py`; Test add to `test_evidence_repository.py`

- [ ] **Step 1: Failing test** using the in-memory object store (find the local/in-memory `ObjectStore` impl used in `tests/storage` or `api` tests as the fixture):

```python
def test_object_store_roundtrip(in_memory_object_store):
    repo = ObjectStoreEvidencePackRepository(in_memory_object_store)
    repo.put("kb1", _pack())
    assert repo.get("kb1", "ev-1").reasoning == "r"
    assert repo.get("kb1", "missing") is None
```

- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** Implement: serialize `pack.model_dump_json()` to key `knowledgebases/{kb}/evidence/{id}.json` via `ObjectStoreProtocol.put_bytes`; `get` reads + `EvidencePack.model_validate_json`, returns `None` on missing key (catch the not-found path like `ObjectStoreAlertProjectionRepository` in `api/_alert_store.py`). `delete_by_kb` lists prefix + deletes.
- [ ] **Step 4:** pytest PASS; pyright clean; ruff clean on `backend/analytics/explainability`.
- [ ] **Step 5:** Commit: `feat(explainability): object-store EvidencePackRepository adapter`.

### Task B3: DI factory + API read path (TDD)

**Files:** Modify `backend/api/dependencies.py`, `backend/api/routers/evidence.py`; Test `backend/tests/api/test_evidence_router.py`

- [ ] **Step 1: Failing test:** with the in-memory evidence repo seeded via dependency override, `GET /evidence-packs/ev-1` returns the pack; unknown id → 404; assert NO `evidence-001`/`evidence-002` seeded ids are returned for a fresh app.
- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** Add `get_evidence_pack_repository()` (object-store when configured else in-memory — mirror `get_alert_repository` at `dependencies.py:788`, storing on `request.app.state`). Repoint the evidence payload factory / `routers/evidence.py` to read from it (KB-scoped). Map `EvidencePack` → `EvidencePackResponse` via the existing mapper (or a new one) — keep `items`/`policy_citations` empty when absent.
- [ ] **Step 4:** pytest PASS.
- [ ] **Step 5:** Commit: `feat(api): serve evidence packs from repository`.

### Task B4: Real worker extraction + de-seed (TDD)

**Files:** Modify `backend/agent/coordinator.py` (replace `build_explainability_context_source` stub ~:461-466 and persist in the explainability stage), `backend/api/state.py` (remove `_seed_evidence_packs` ~:732-740 and `_build_explainability_contexts` ~:695-730 from the prod path); Test `backend/tests/agent/test_explainability_stage.py`

- [ ] **Step 1: Failing test:** build a synthetic Medicare graph (provider/claim/beneficiary + relationships) in an in-memory graph service + in-memory risk signals; run the explainability stage for an alert seeded on `provider-X`; assert the persisted `EvidencePack` has `subgraph_nodes` drawn from `graph.get_subgraph` (not constants) and `scores` populated from the risk assessment.
- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** Implement a `ServiceBackedExplainabilityContextSource` (define in `agent/` — orchestrator owns cross-service composition) taking graph + risk + entity-metric protocols; for an alert it calls `graph.get_subgraph(kb, seeds, depth=2)`, `risk.assess(...)`, and metric lookups → builds `ExplanationContext`. Wire it into `build_explainability_context_source`. After `ExplainabilityService.generate`, persist via `EvidencePackRepository.put` (best-effort: wrap in try/except, log + emit a recovery marker on failure, never raise).
- [ ] **Step 4:** pytest PASS. Remove the seeding methods from `ApiState` prod path; run `backend/.venv/bin/python -m pytest backend/tests/api -k "evidence or state" -v` and fix fallout.
- [ ] **Step 5:** `pyright --strict` on `backend/agent`, `backend/analytics/explainability`, `backend/api`; ruff clean; full `backend/.venv/bin/python -m pytest backend/tests/agent backend/tests/analytics/explainability backend/tests/api --cov` ≥85% on touched packages.
- [ ] **Step 6:** Commit: `feat(agent): real evidence-pack extraction + de-seed ApiState (BL-005)`.

### Task B5: BL-005 run-and-verify checkpoint

- [ ] **Step 1:** `make dev` (or host API+worker), ingest a small KB, trigger analytics/alerting, confirm an alert's `evidence_pack_id` resolves via `GET /evidence-packs/{id}` to a pack whose subgraph ids exist in the graph. Capture logs/response.
- [ ] **Step 2:** Flip `monitoring.06` AC boxes + status in `docs/backlog/monitoring.md`, and `graph.05` in `docs/backlog/graph.md`, as their criteria are met; run `python scripts/backlog_consistency.py`.
- [ ] **Step 3:** Commit: `chore(backlog): mark BL-005 backend stories progressed`.

---

## Phase C — Cases module (BL-010 backend)

### Task C1: Domain model + exceptions

**Files:** Create `backend/cases/__init__.py`, `backend/cases/models.py`, `backend/cases/exceptions.py`

- [ ] **Step 1:** Write `Case` + `CaseTimelineEvent` Pydantic models per spec §4.1; `CaseError`/`CasePersistenceError`/`CaseNotFoundError` in exceptions.
- [ ] **Step 2:** `pyright --strict backend/cases` clean.
- [ ] **Step 3:** Commit: `feat(cases): domain model + exceptions`.

### Task C2: Repository protocol + in-memory (TDD)

**Files:** Create `backend/cases/adapters/__init__.py`, `adapters/protocols.py`, `adapters/in_memory.py`; Test `backend/tests/cases/test_in_memory_store.py`

- [ ] **Step 1: Failing tests** (CRUD, KB isolation, status/priority filter, pagination total) — model on `backend/tests/records/test_in_memory_store.py`.
- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** Implement `CaseRepository` protocol (spec §4.1) + `InMemoryCaseRepository` (dict keyed `(kb, id)`; `list` filters + returns `(items, total)`; sort `updated_at desc`).
- [ ] **Step 4:** pytest PASS; pyright clean.
- [ ] **Step 5:** Commit: `feat(cases): repository protocol + in-memory adapter`.

### Task C3: Migration + Postgres adapter (TDD, integration-gated)

**Files:** Create `backend/database/migrations/versions/0002_cases.py`, `backend/cases/adapters/postgres.py`; Test `backend/tests/cases/test_postgres_store.py`

- [ ] **Step 1:** Write `0002_cases.py` (spec §4.2 SQL, `down_revision="0001_persistence_baseline"`).
- [ ] **Step 2: Failing `@pytest.mark.integration` test** modeled on `backend/tests/records/test_postgres_store.py` (create/get/list/update, idempotent upsert, KB isolation, DELETE-cleanup).
- [ ] **Step 3:** Implement `PostgresCaseRepository(provider)` (spec §4.1): module SQL constants, `%s::jsonb` for `alert_ids`/`timeline`, `ON CONFLICT (knowledge_base_id, case_id) DO UPDATE`, `_row_to_case` with explicit casts + `Literal` validation, re-raise as `CasePersistenceError`. psycopg-free (depend on `database/protocols.py`).
- [ ] **Step 4:** Run migration against local PG (`make dev`) + integration test → PASS (or note integration-gated if PG unavailable); `pyright --strict backend/cases` clean.
- [ ] **Step 5:** Commit: `feat(cases): postgres adapter + 0002_cases migration`.

### Task C4: Service (promote-from-alert) (TDD)

**Files:** Create `backend/cases/service.py`, `backend/cases/service_models.py`; Test `backend/tests/cases/test_service.py`

- [ ] **Step 1: Failing test:** `CaseService.promote_from_alert(kb, alert, evidence_pack, timeline)` returns a `Case` with `originating_alert_id`, `evidence_pack_id`, `alert_ids=[alert.id]`, snapshot `timeline`, `status="open"`, and persists via the repo (use in-memory repo + stub inputs).
- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** Implement `CaseService` (create/get/list/update + `promote_from_alert`).
- [ ] **Step 4:** pytest PASS; pyright clean.
- [ ] **Step 5:** Commit: `feat(cases): service with promote-from-alert`.

### Task C5: Contracts + OpenAPI regen

**Files:** Modify `backend/api/contracts.py`

- [ ] **Step 1:** Add `knowledge_base_id` to `CaseSummaryResponse` + `CaseCreateRequest`; add `CasePromoteRequest{alert_id, notes?}`; extend `CaseDetailResponse` with `evidence_pack: EvidencePackResponse | None` + `entity_timeline: list[CaseTimelineEventResponse]`; add `CaseTimelineEventResponse`.
- [ ] **Step 2:** `python tools/export_openapi.py` then `cd chili_app && npm run codegen:api`; verify `git diff` shows updated `openapi.json`/`schema.ts`.
- [ ] **Step 3:** Commit: `feat(api): KB-scoped case contracts + promote request (regen OpenAPI)`.

### Task C6: DI + router + analytics ripples (TDD)

**Files:** Modify `backend/api/dependencies.py`, `backend/api/routers/cases.py`, `backend/api/state.py`; Test `backend/tests/api/test_cases_router.py`, `backend/tests/api/test_case_repository_selection.py`

- [ ] **Step 1: Failing tests:** CRUD with `?knowledge_base_id=` (viewer reads / analyst writes via RBAC), KB-scoping (case in kb1 not visible from kb2), status/priority filter, `POST /cases/promote` capturing evidence pack + timeline; plus a backend-selection test (in-memory vs postgres via `get_connection_provider`).
- [ ] **Step 2:** pytest → FAIL.
- [ ] **Step 3:** Add `get_case_repository()` (`provider is None → in-memory else postgres`) + `get_case_service()`; rewrite case payload factories to use the service; update `routers/cases.py` with `knowledge_base_id: str = Query(...)`, filters, and `POST /cases/promote` (loads Alert via projection repo + EvidencePack via evidence repo + timeline via timeseries). KB-scope `AnalyticsOverviewResponse.open_cases` (`state.py:371`) and `list_policy_gap_cases` (`state.py:330`). Remove `_seed_cases` from prod path.
- [ ] **Step 4:** pytest PASS; `pyright --strict backend/api backend/cases` clean; ruff clean; `pytest backend/tests/api backend/tests/cases --cov` ≥85% on touched packages.
- [ ] **Step 5:** Commit: `feat(api): KB-scoped cases CRUD + promote-from-alert (BL-010)`.

### Task C7: BL-010 backend run-and-verify checkpoint

- [ ] **Step 1:** Run API; create a case under a KB, list it (scoped), patch it, promote an alert → confirm DB row (PG) / state and `CaseDetailResponse.evidence_pack` populated. Capture responses.
- [ ] **Step 2:** Commit: `chore(backlog): mark BL-010 backend progressed`.

---

## Phase D — Frontend (BL-006 + BL-010 finish)

### Task D1: Shared subgraph util

**Files:** Create `chili_app/src/api/subgraph.ts`; Modify `InvestigationWorkbenchPage.tsx`

- [ ] **Step 1:** Move `toSubgraphResult` (currently private at `InvestigationWorkbenchPage.tsx:367-394`) into `src/api/subgraph.ts` as an exported fn; import it in the workbench. Run `cd chili_app && npm run test:run -- InvestigationWorkbenchPage` → still PASS; `npm run lint`.
- [ ] **Step 2:** Commit: `refactor(fe): extract toSubgraphResult util`.

### Task D2: EvidencePackViewer component (TDD)

**Files:** Create `chili_app/src/components/investigation/EvidencePackViewer.tsx`; Test `__tests__/EvidencePackViewer.test.tsx` (replace stale `EvidencePanel.tsx`)

- [ ] **Step 1: Failing Vitest** (mock `useEvidencePack` + `useInvestigationNeighborhood`): asserts it renders reasoning, each item (source_type/quote/rationale), the metrics snapshot (scores keys + confidence), policy citations, and mounts `GraphCanvas` with resolved subgraph nodes.
- [ ] **Step 2:** `npm run test:run -- EvidencePackViewer` → FAIL.
- [ ] **Step 3:** Implement consuming `EvidencePackResponse` from `src/api/contracts.ts`; resolve `subgraph_node_ids` via `useInvestigationNeighborhood` + `toSubgraphResult` → `GraphCanvas`. Delete the stale `EvidencePanel.tsx` + its test.
- [ ] **Step 4:** test PASS; `npm run lint`; `npx tsc -b`.
- [ ] **Step 5:** Commit: `feat(fe): EvidencePackViewer with subgraph render (BL-006)`.

### Task D3: Wire viewer into Workbench + Alert Feed (TDD)

**Files:** Modify `InvestigationWorkbenchPage.tsx` (replace inline block :311-325), `AlertFeedPage.tsx` (add "View evidence" action)

- [ ] **Step 1:** Update `InvestigationWorkbenchPage.test.tsx` + `AlertFeedPage` test to assert the viewer/action appears; run → FAIL.
- [ ] **Step 2:** Implement; respect `AnalystCopy.test.tsx` (no seeded/demo copy).
- [ ] **Step 3:** tests PASS; lint + tsc.
- [ ] **Step 4:** Commit: `feat(fe): evidence viewer in workbench + alert feed (BL-006)`.

### Task D4: CaseManagementPage finish (TDD)

**Files:** Modify `CaseManagementPage.tsx`, `src/api/cases.ts`

- [ ] **Step 1:** Update `CaseManagementPage.test.tsx`: assert `?kb=` threading, status/priority FilterBar, edit form (title/priority/assignee), toast on mutation, promote-from-alert. Run → FAIL.
- [ ] **Step 2:** Implement: thread `?kb=` via `useSearchParams`; add FilterBar (copy AlertFeedPage pattern); add edit form (CreateKbForm pattern) calling `useUpdateCase`; add `showToast` in mutation `onSuccess/onError`; add a `usePromoteCase` mutation hitting `POST /cases/promote`.
- [ ] **Step 3:** tests PASS; lint + tsc.
- [ ] **Step 4:** Commit: `feat(fe): finish CaseManagementPage (filter/edit/toast/promote) (BL-010)`.

### Task D5: e2e

**Files:** Modify `chili_app/e2e/investigation-workbench.spec.ts`, `alert-feed.spec.ts`, `case-management.spec.ts`, `e2e/helpers/mocks.ts`

- [ ] **Step 1:** Add `mockEvidencePack` helper; add evidence-render assertions to workbench + alert-feed specs; add KB-scoped case + promote-flow assertions to case-management spec.
- [ ] **Step 2:** `cd chili_app && npm run test:e2e -- investigation-workbench alert-feed case-management`. Expected: PASS.
- [ ] **Step 3:** Commit: `test(e2e): evidence viewer + case promote flows`.

---

## Phase E — Docs, backlog, final verification

### Task E1: Docs

- [ ] **Step 1:** Write `backend/cases/README.md`; add evidence-repo note to `backend/analytics/explainability/README.md`; update `backend/README.md` (new `cases` module + `cases` table) and `docs/architecture.md` (evidence/case data flows + `get_subgraph` + module decomposition).
- [ ] **Step 2:** Commit: `docs: cases module, evidence flow, get_subgraph`.

### Task E2: Backlog + sprint status

- [ ] **Step 1:** Flip `frontend.02`, `rag.10`, `monitoring.06`, `graph.05` AC/status as met; in `docs/project/planning/backlog.md` set BL-005/BL-006/BL-010 → `done` and D-06/D-07 → RESOLVED; update `docs/project/planning/sprints/2026-23.md` story statuses. Run `python scripts/backlog_consistency.py` (and `--check`).
- [ ] **Step 2:** Commit: `docs(backlog): close BL-005/006/010 for sprint 2026-23`.

### Task E3: Full green gate

- [ ] **Step 1:** `backend/.venv/bin/python -m pytest backend/tests --cov` full green, ≥85% per touched package; `backend/.venv/bin/pyright`; `backend/.venv/bin/ruff check backend`.
- [ ] **Step 2:** `cd chili_app && npm run lint && npm run test:run && npm run build`.
- [ ] **Step 3:** Run the full stack and execute the sprint demo (spec §8 DoD): alert → evidence pack (subgraph+metrics+reasoning) → promote to case → case persisted/listed, against `medicare_fraud`.
- [ ] **Step 4:** Commit any final fixes; summarize verified status.

---

## Self-Review

**Spec coverage:** §2 get_subgraph → Phase A. §3 evidence repo/extraction/de-seed/read → Phase B (B1-B5). §4 cases module/migration/DI/contracts/router/ripples → Phase C (C1-C7). §5 frontend viewer + cases finish → Phase D (D1-D5). §8 quality gates → embedded per task + E3. §9 docs → E1/E2. All spec sections map to tasks.

**Placeholder scan:** Code steps include real signatures/SQL/test bodies; boilerplate-heavy adapters/tests explicitly reference the in-repo template files to copy (records/monitoring adapters, existing page/e2e tests) rather than leaving "TODO" — acceptable given the executor has the exploration map. No "TBD"/"add error handling"-style gaps.

**Type consistency:** `get_subgraph(knowledge_base_id, seed_entity_ids, depth)` identical across A1/A2/A3/A4 and B4. `EvidencePackRepository.{put,get,delete_by_kb}` consistent B1→B4. `CaseRepository.{create,get,list,update,delete_by_kb}` + `Case`/`CaseTimelineEvent` consistent C1→C6. `EvidencePack` shape unchanged (shared type). Endpoints `GET/POST/PATCH /cases?knowledge_base_id=` + `POST /cases/promote` consistent C5/C6/D4.
