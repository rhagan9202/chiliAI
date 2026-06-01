# Design: Evidence-Pack Vertical & Case Management v1 (Sprint 2026-23)

> Status: approved 2026-06-01 · Sprint: [2026-23](../../project/planning/sprints/2026-23.md)
> Stories: **BL-005** (evidence pack subgraph extraction), **BL-006** (evidence pack on alert UI), **BL-010** (Case Management v1)
> Requirements: REQ-ANALYTICS-005, REQ-ALERT-003, REQ-CASE-001..004
> Module backlog stories advanced: graph.05, monitoring.06, rag.10, frontend.02

## 1. Context & scope correction

Sprint 2026-23 delivers the **alert → evidence → case** investigative vertical. Code exploration on 2026-06-01 corrected the sprint's greenfield assumption:

- **Frontend is largely built.** `CaseManagementPage`, `/cases` hooks, unit tests, and e2e specs (`case-management`, `case-mutation`, `case-feedback`) already exist on `prod`. The Investigation Workbench already renders evidence `reasoning` + `items` inline (`InvestigationWorkbenchPage.tsx:311-325`).
- **Backend is seeded/ephemeral.** Cases live in `ApiState` in-process dicts (`api/state.py:92-100 CaseRecord`, `_seed_cases` at `:742`) — not durable, **not KB-scoped**. Evidence packs are served entirely from seeded `ApiState` (`_seed_evidence_packs` at `:732-740`, `_build_explainability_contexts` at `:695-730` hardcode subgraph ids/scores/confidence). The worker's explainability context source is an empty stub (`agent/coordinator.py:461-466`). `get_subgraph` does not exist (`graph/protocols.py:17-18` TODO).

Therefore the work concentrates on **backend persistence + real extraction**, with the frontend a finish/relocate job.

### Design decisions (confirmed with stakeholder)
1. **EvidencePack persistence**: object-store + in-memory `EvidencePackRepository` (co-located with the alert projection family). No new Postgres table for evidence this sprint.
2. **Subgraph extraction**: add `get_subgraph(kb_id, seed_ids, depth)` to the graph protocol + adapters (advances graph.05) — traversal lives in `graph/`, not in the evidence builder.
3. **Case KB-scoping**: cases become KB-scoped now (breaking contract change), per REQ-CASE-004.

### Non-goals (explicit YAGNI)
- No change to the shared `EvidencePack` type shape (id-lists + `scores` dict are sufficient; the metric snapshot rides in `scores`).
- No Postgres adapter for evidence packs (object-store only this sprint).
- No token-level streaming, no multi-analyst evidence collaboration, no evidence versioning (requirements §6 out-of-scope).
- No GNN-derived subgraphs; traversal is bounded BFS over persisted relationships.

## 2. Foundation — `graph.get_subgraph`

**Contract.** Add to `GraphServiceProtocol` (`graph/protocols.py`) and `GraphRepository` (`graph/adapters/protocols.py`):

```python
def get_subgraph(
    self,
    knowledge_base_id: str,
    seed_entity_ids: list[str],
    depth: int = 1,
) -> SubgraphResult: ...
```

- Returns `SubgraphResult(entities: list[Entity], relationships: list[Relationship])` (`graph/models.py:34-38`) — the **union** of the `depth`-hop neighborhoods of every seed, deduplicated by entity/relationship id. Empty seed list → empty result. Seeds absent from the graph are skipped (not an error). KB scoping enforced at the protocol boundary (REQ-GRAPH-002).
- Remove the `get_subgraph` TODO at `graph/protocols.py:17-18` and `graph/service.py:29-31`.

**Adapters.**
- `in_memory.py`: generalize the existing single-seed BFS (`in_memory.py:84-139`) to accept a seed set — seed the frontier with all `seed_entity_ids`, expand to `depth`, collect visited entities + traversed relationships, dedup.
- `neo4j_adapter.py`: one parameterized Cypher over the seed list, e.g.
  `MATCH (s:Entity) WHERE s.kb_id = $kb AND s.id IN $seeds MATCH p = (s)-[*0..$depth]-(n:Entity {kb_id:$kb}) ...` returning distinct nodes + relationships; routed through `_run_read` / the active transaction. (Variable-length bound interpolated as a validated int literal — driver params cannot parameterize `*0..n`.)

**Tests.** `tests/graph/test_in_memory.py`: multi-seed union, dedup, depth bound, missing seed, empty seeds, KB isolation. Neo4j: `@pytest.mark.integration` rollback-safe test asserting the same union semantics.

## 3. BL-005 — real evidence-pack extraction & persistence

### 3.1 Repository
New under `analytics/explainability/` (cohesive with the generator):
- `analytics/explainability/repository.py` — `EvidencePackRepositoryProtocol`:
  ```python
  def put(self, knowledge_base_id: str, pack: EvidencePack) -> None: ...
  def get(self, knowledge_base_id: str, evidence_pack_id: str) -> EvidencePack | None: ...
  def delete_by_kb(self, knowledge_base_id: str) -> int: ...
  ```
- `adapters/in_memory.py` — dict keyed `(kb_id, evidence_pack_id)`.
- `adapters/object_store.py` — serializes the pack to JSON under `knowledgebases/{kb_id}/evidence/{evidence_pack_id}.json` via the shared `ObjectStoreProtocol` (`shared/protocols.py:39-58`), matching the `ObjectStoreAlertProjectionRepository` pattern in `api/_alert_store.py`.

### 3.2 Real extraction in the worker
The explainability stage runs in the worker coordinator (`agent/`), which is the sanctioned orchestrator for cross-service calls (CLAUDE.md Hard Rule 1).

- Replace the empty `build_explainability_context_source` stub (`coordinator.py:461-466`) with a **service-backed context source** (constructed in the worker, taking the graph, risk, and entity-metric services/protocols by injection). For an alert's seed entities it builds an `ExplanationContext` (`analytics/explainability/models.py:33-47`):
  - `subgraph` node/edge ids from `graph.get_subgraph(kb, seeds, depth)` (depth is fixed/bounded per R-03; document the value).
  - `items` from the strongest contributing entities/relationships (source_id/source_type/quote/rationale/score).
  - `scores` dict from `risk.assess(...)` (`overall_score` + top `factors`) plus per-entity metrics from `EntityMetricRepository` — this is the "metric snapshot."
- `ExplainabilityService.generate(context)` (`analytics/explainability/service.py:57-65`) produces the `EvidencePack` (unchanged).
- The coordinator persists the generated pack via `EvidencePackRepository.put` (keyed by kb + `evidence_pack_id`). **Best-effort**: on failure, log + emit an ingestion-style recovery marker; the alert still carries `evidence_pack_id`, and `GET` returns 404 until the pack lands. Persistence failure never fails the alert/analytics pipeline.

### 3.3 API read path & de-seed
- `GET /evidence-packs/{id}` (`api/routers/evidence.py`) resolves via a new DI factory `get_evidence_pack_repository()` (object-store when configured, else in-memory — mirroring `get_alert_repository`) instead of `state.get_evidence_pack`.
- Remove `_seed_evidence_packs` (`state.py:732-740`) and `_build_explainability_contexts` (`state.py:695-730`) from the production path (move to a dev seed tool if needed for demos).
- De-seed regression test (mirrors analytics.28's `test_default_router_returns_empty_results_with_no_seed_data`): with no generated packs, the endpoint returns 404, no hardcoded `evidence-001/002` leaks.

### 3.4 Tests
- Context source unit test with a synthetic Medicare scenario (provider/claim/beneficiary entities + relationships + risk signals): assert the pack's subgraph ids and scores come from the graph/risk inputs, not constants.
- `EvidencePackRepository` in-memory + object-store round-trip; `delete_by_kb`.
- Worker stage: pack persisted on explainability; best-effort failure path leaves the pipeline green.

## 4. BL-010 — durable, KB-scoped Case Management

### 4.1 `backend/cases/` module (mirrors `records/`)
- `models.py` — internal `Case`:
  ```python
  class Case(BaseModel):
      id: str
      knowledge_base_id: str
      title: str
      status: Literal["open", "in_review", "closed"]
      priority: Literal["low", "medium", "high", "critical"]
      assignee: str | None
      originating_alert_id: str | None
      evidence_pack_id: str | None
      alert_ids: list[str]
      timeline: list[CaseTimelineEvent]   # snapshot captured at promote time
      created_at: datetime
      updated_at: datetime
  ```
  `CaseTimelineEvent` (ts, label, detail) captures the entity timeline snapshot at promotion.
- `adapters/protocols.py` — `CaseRepository` (`@runtime_checkable`):
  ```python
  def create(self, case: Case) -> Case: ...
  def get(self, *, knowledge_base_id: str, case_id: str) -> Case | None: ...
  def list(self, *, knowledge_base_id: str, limit: int, offset: int,
           status: str | None = None, priority: str | None = None) -> tuple[list[Case], int]: ...
  def update(self, case: Case) -> Case: ...
  def delete_by_kb(self, knowledge_base_id: str) -> int: ...
  ```
- `adapters/in_memory.py` — dict keyed `(kb_id, case_id)`, filter by kb/status/priority, deterministic sort by `updated_at desc` (template: `records/adapters/in_memory.py`).
- `adapters/postgres.py` — `PostgresCaseRepository(provider: ConnectionProvider)`, module-level SQL constants, `%s::jsonb` for `alert_ids`/`timeline`, `ON CONFLICT (knowledge_base_id, case_id) DO UPDATE` for upsert on `update`/idempotent `create`, `_row_to_case` with explicit casts and `Literal` validation. psycopg-free (depends only on `database/protocols.py`). Re-raises as `CasePersistenceError`.
- `exceptions.py` — `CaseError`, `CasePersistenceError`, `CaseNotFoundError`.
- `service.py` — thin orchestration (`promote_from_alert` composes alert + evidence pack + timeline → `Case`).

### 4.2 Migration `0002_cases.py`
`revision="0002_cases"`, `down_revision="0001_persistence_baseline"`. Raw SQL via `op.execute` (baseline style):
```sql
CREATE TABLE cases (
  knowledge_base_id text NOT NULL,
  case_id           text NOT NULL,
  title             text NOT NULL,
  status            text NOT NULL,
  priority          text NOT NULL,
  assignee          text,
  originating_alert_id text,
  evidence_pack_id  text,
  alert_ids         jsonb NOT NULL DEFAULT '[]'::jsonb,
  timeline          jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (knowledge_base_id, case_id)
);
CREATE INDEX ix_cases_status ON cases (knowledge_base_id, status, updated_at DESC);
```
`downgrade()` drops the index + table.

### 4.3 DI, contracts, router
- `get_case_repository()` (`@lru_cache`) — `provider = get_connection_provider(); return InMemoryCaseRepository() if provider is None else PostgresCaseRepository(provider)` (records/monitoring template at `dependencies.py:727`).
- Contracts (`api/contracts.py`): add `knowledge_base_id` to `CaseSummaryResponse` + `CaseCreateRequest`; add `CasePromoteRequest { alert_id, notes? }`; extend `CaseDetailResponse` with `evidence_pack: EvidencePackResponse | None` and `entity_timeline: list[...]`.
- Router (`api/routers/cases.py`): all routes take `knowledge_base_id: str = Query(...)`; `GET` reads scoped (viewer), `POST/PATCH` write scoped (analyst), filters `status`/`priority` on `GET`. Add `POST /cases/promote` (analyst): loads the `Alert` (projection repo) + its `EvidencePack` (evidence repo) + entity timeline (timeseries) and persists a `Case`.
- Ripples: `AnalyticsOverviewResponse.open_cases` (`state.py:371`) and `list_policy_gap_cases` (`state.py:330`) become KB-scoped reads against the repository.
- Replace direct `state.create_case/...` calls in the case payload factories with repository-backed calls; remove `_seed_cases` from the production path.
- After Pydantic changes: `tools/export_openapi.py` → `npm run codegen:api` → update `contracts.ts` aliases (Hard Rule 5; CI drift gate enforces it).

### 4.4 Tests
- `tests/cases/test_in_memory_store.py` (CRUD, filter, KB isolation, pagination).
- `tests/cases/test_postgres_store.py` (`@pytest.mark.integration`, idempotent upsert, DELETE-cleanup).
- `tests/api/test_cases_router.py` (CRUD, RBAC viewer/analyst, KB-scoping, promote-from-alert capturing evidence + timeline).
- `tests/api/test_case_repository_selection.py` (backend selection like `test_monitoring_source_selection.py`).
- Coverage ≥85% per touched package.

## 5. BL-006 — evidence-pack viewer (frontend finish)

- Promote `toSubgraphResult` (private at `InvestigationWorkbenchPage.tsx:367-394`) to a shared util `src/api/subgraph.ts`.
- New `src/components/investigation/EvidencePackViewer.tsx` consuming `EvidencePackResponse` from `src/api/contracts.ts`: renders `reasoning`, `items[]` (source_type/quote/rationale/score), a **metrics snapshot** (`scores` map + `confidence`), `policy_citations`, and the **subgraph via `GraphCanvas`** — resolving `subgraph_node_ids` against `useInvestigationNeighborhood` + `toSubgraphResult`. (Replaces the stale `EvidencePanel.tsx` stub.)
- Wire into Investigation Workbench (replace inline block `:311-325`) and add a "View evidence" action on Alert Feed rows using `alert.evidence_pack_id` + `useEvidencePack`.
- CaseManagementPage finish: thread `?kb=` via `useSearchParams` (pattern at `InvestigationWorkbenchPage.tsx:43,134,171`), add status/priority `FilterBar`, an edit form (title/priority/assignee via `useUpdateCase`), `showToast` on mutations, and a fuller promote-from-alert path.
- Tests: Vitest for `EvidencePackViewer` (mock `useEvidencePack` + neighborhood); update `InvestigationWorkbenchPage.test.tsx`; respect `AnalystCopy.test.tsx` (no seeded/demo copy). Playwright: add evidence-render assertions to `e2e/investigation-workbench.spec.ts` + `e2e/alert-feed.spec.ts` (new `mockEvidencePack` helper), KB-scoped case mocks + promote flow to `e2e/case-management.spec.ts`.

## 6. Data flows

**Evidence:** records/docs → graph build → analytics (risk/metrics) → monitoring `AlertsCreatedEvent` → worker explainability stage: `graph.get_subgraph(seeds)` + `risk.assess` + entity metrics → `ExplanationContext` → `ExplainabilityService.generate` → `EvidencePack` → `EvidencePackRepository.put` (object store). API `GET /evidence-packs/{id}` → `repository.get`. Frontend resolves subgraph ids → `GraphCanvas`.

**Promote-to-case:** analyst clicks promote (Alert Feed / workbench) → `POST /cases/promote?knowledge_base_id=` `{alert_id}` → backend loads Alert (projection) + EvidencePack (repo) + timeline (timeseries) → `Case(kb, originating_alert_id, evidence_pack_id, alert_ids, timeline, status=open)` → `CaseRepository.create` → `CaseDetailResponse`.

## 7. Error handling

- `get_subgraph`: missing seeds skipped; unknown KB → existing `GraphError`; depth validated as a positive int.
- Evidence persistence (worker): best-effort with recovery marker; never fails the pipeline.
- `GET /evidence-packs/{id}`: pack not yet generated → 404.
- Cases: alert not found on promote → 404; KB mismatch → 404; Postgres failures re-raised as `CasePersistenceError`; `create` idempotent via upsert.

## 8. Testing & quality gates

- `pyright --strict` clean on every touched backend package (note dev-env constraint: avoid `@contextmanager`+`Iterator`; follow `ConnectionProvider.connection() -> AbstractContextManager`).
- pytest ≥85% per touched package, full green; integration tests gated by `@pytest.mark.integration`.
- ruff clean; ESLint clean; `tsc -b` strict; `npm run test:run` + targeted Playwright e2e.
- Verify by running the API + worker (logs/DB/responses) and the app (rendering/interaction), not code review alone.

## 9. Documentation updates

- New: `backend/cases/README.md`, evidence-repo note in `analytics/explainability/README.md`.
- Update: `backend/README.md` (new module + `cases` table + any env), `docs/architecture.md` (evidence/case data flows, `get_subgraph`, new module decomposition).
- Backlog: flip `graph.05`/`monitoring.06`/`frontend.02`/`rag.10` statuses as their ACs land; `docs/project/planning/backlog.md` BL-005/006/010 → `done` (+ D-06/D-07 RESOLVED) at sprint completion; update `docs/project/planning/sprints/2026-23.md` status.

## 10. Build order (sequenced, TDD, checkpointed)

1. `graph.get_subgraph` (protocol + adapters + tests) — **foundation**.
2. `EvidencePackRepository` (protocol + in-memory + object-store) — freezes the contract dependents build against.
3. Worker real context source + persist + de-seed; API read path → repo. **[BL-005 complete]**
4. `backend/cases/` module + migration + DI + contracts + router + analytics ripples; regen OpenAPI. **[BL-010 backend]**
5. Frontend `EvidencePackViewer` + Alert Feed entry + workbench wiring; CaseManagementPage kb/filter/edit/promote; regen contracts. **[BL-006 + BL-010 FE]**
6. Full test pass + run-and-verify + docs/backlog updates.

Each numbered step is landed and verified (tests green, types clean) before the next; status reported at each checkpoint.
