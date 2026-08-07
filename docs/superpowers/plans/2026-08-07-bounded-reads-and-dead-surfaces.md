# Bounded Reads and Dead Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the last unbounded entity read, give the WebSocket alert stream a producer, and make a parked run visible where operators actually look.

**Architecture:** No new machinery. `get_entities_by_type` already establishes the paginated read shape; the alert stream already has a hub, filters and a subscriber protocol and is missing only the bridge; the dashboard already renders workflow status and is missing one branch.

**Tech Stack:** Python 3.12, FastAPI, Neo4j, Redis Streams, React 19 + TypeScript, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-07-execution-gap-closure-design.md` §2 Tiers 3–4

**Depends on:** nothing. Independent of Plans 1 and 2 and safe to run in parallel with either.

## Global Constraints

- Python 3.12. Full type annotations; **no `Any`**. Bare `backend/.venv/bin/pyright` must report 0 errors.
- `backend/.venv/bin/ruff check --no-cache .` must pass.
- Frontend: TypeScript strict, ESLint clean. Import DTOs from `chili_app/src/api/contracts.ts`; never hand-write wire types, never `as any`.
- **A frontend contract change is not verified until `npm run build` passes** — `tsc --noEmit` does not check the referenced project config (spec §4.5).
- Coverage ≥ 85% per package.

## Verification Doctrine (inherited — spec §4)

1. **Break the guard to prove it works.**
2. **In-process tests cannot discover unreachability** — Task 3 and Task 6 run against the live stack.
3. **Assert the projection a client receives**, not the record behind it.

## File Structure

| File | Responsibility |
|---|---|
| `backend/graph/adapters/protocols.py` | `get_entities_page` on the protocol |
| `backend/graph/adapters/{in_memory,neo4j_adapter}.py` | implementations |
| `backend/analytics/score_runs/executor.py` | page through enumeration |
| `backend/analytics/gnn/adapters/graph_repository_source.py` | page through the snapshot read |
| `backend/api/routers/ws.py` | subscribe the hub to the event bus |
| `backend/monitoring/service.py` *(or the alert publisher)* | publish `AlertCreatedEvent` |
| `chili_app/src/pages/DashboardPage.tsx` | count and surface `awaiting_approval` |

---

### Task 1: A bounded entity read

**Files:**
- Modify: `backend/graph/adapters/protocols.py`, `backend/graph/adapters/in_memory.py`, `backend/graph/adapters/neo4j_adapter.py`
- Test: `backend/tests/graph/test_in_memory.py`, `backend/tests/graph/test_neo4j_adapter.py`

**Interfaces:**
- Produces: `get_entities_page(knowledge_base_id: str, *, limit: int, offset: int) -> list[Entity]`

`get_entities` has **no LIMIT at all** — it materialises every entity in one
query. `get_entities_by_type(kb, type, limit, offset)` already exists and is
genuinely paginated, so copy its shape minus the type predicate. Same ordering
(`ORDER BY entity.entity_id`), because a page sequence is only resumable if the
order is deterministic across calls.

- [ ] **Step 1: Write the failing tests**

```python
def test_get_entities_page_returns_a_bounded_deterministic_slice() -> None:
    repository = InMemoryGraphRepository()
    repository.upsert_entities("kb-1", [Entity(id=f"e-{i:03d}", type="provider")
                                        for i in range(10)])

    first = repository.get_entities_page("kb-1", limit=4, offset=0)
    second = repository.get_entities_page("kb-1", limit=4, offset=4)

    assert [e.id for e in first] == ["e-000", "e-001", "e-002", "e-003"]
    assert [e.id for e in second] == ["e-004", "e-005", "e-006", "e-007"]


def test_paging_past_the_end_returns_empty_not_an_error() -> None:
    """The enumeration loop's termination condition."""
    repository = InMemoryGraphRepository()
    repository.upsert_entities("kb-1", [Entity(id="e-1", type="provider")])

    assert repository.get_entities_page("kb-1", limit=10, offset=10) == []


def test_pages_reassemble_into_exactly_the_unpaged_result() -> None:
    """The property that matters: paging must not drop or duplicate an entity."""
    repository = InMemoryGraphRepository()
    repository.upsert_entities("kb-1", [Entity(id=f"e-{i:03d}", type="provider")
                                        for i in range(25)])

    paged: list[str] = []
    offset = 0
    while page := repository.get_entities_page("kb-1", limit=7, offset=offset):
        paged.extend(e.id for e in page)
        offset += 7

    assert paged == sorted(e.id for e in repository.get_entities("kb-1"))
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/graph/test_in_memory.py -k page -v`
Expected: FAIL — no such method

- [ ] **Step 3: Implement on the protocol and both adapters**

Neo4j, mirroring `get_entities_by_type` exactly minus the `WHERE`:

```python
        query = f"""
        MATCH (entity:{_ENTITY_LABEL} {{knowledge_base_id: $knowledge_base_id}})
        RETURN entity
        ORDER BY entity.entity_id
        SKIP $offset
        LIMIT $limit
        """
```

Document the known cost: `SKIP` is O(offset) in Neo4j, so deep pagination
degrades. A keyset cursor (`WHERE entity.entity_id > $after`) is the fix if that
becomes real; it is deliberately not done here (spec §6) because it changes the
protocol shape and the existing by-type method would then disagree with it.

Leave `get_entities` in place. It has callers beyond the two being changed, and
removing it is a separate, wider change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/graph/ -v`
For the Neo4j adapter: `.venv/bin/pytest tests/graph/test_neo4j_adapter.py -v -m integration`
with the stack up.

- [ ] **Step 5: Commit**

```bash
git add backend/graph backend/tests/graph
git commit -m "feat(graph): add a bounded, deterministic entity page read"
```

---

### Task 2: Page through score-run enumeration

**Files:**
- Modify: `backend/analytics/score_runs/executor.py`
- Test: `backend/tests/analytics/score_runs/test_executor.py`

`handle_score_run_queued` calls `graph_repository.get_entities(...)`, which
loads every entity in the knowledge base into memory. Moving enumeration into
the worker (2026-08-06) made it retryable and got it out of the HTTP request,
but it is still one unbounded read.

- [ ] **Step 1: Write the failing test**

```python
def test_enumeration_pages_rather_than_materialising_every_entity() -> None:
    """Risk R2, second half. Moving enumeration into the worker made the read
    retryable; it did not make it bounded."""

    class _CountingGraphRepository(InMemoryGraphRepository):
        def __init__(self) -> None:
            super().__init__()
            self.unbounded_calls = 0
            self.page_calls = 0

        def get_entities(self, knowledge_base_id: str) -> list[Entity]:
            self.unbounded_calls += 1
            return super().get_entities(knowledge_base_id)

        def get_entities_page(self, knowledge_base_id: str, *, limit: int, offset: int):
            self.page_calls += 1
            return super().get_entities_page(knowledge_base_id, limit=limit, offset=offset)

    repository = _CountingGraphRepository()
    repository.upsert_entities("kb-1", [Entity(id=f"e-{i:03d}", type="provider")
                                        for i in range(250)])
    deps = _deps(graph_repository=repository)

    handle_score_run_queued(_run_queued_event(batch_size=100), deps)

    assert repository.unbounded_calls == 0
    assert repository.page_calls >= 3


def test_enumeration_covers_every_entity_exactly_once() -> None:
    """A paging bug that drops entities is worse than an unbounded read:
    the run completes successfully having scored a subset."""
    ...
    batches = repository_under_test.list_batches(run_id=_RUN_ID)
    enumerated = [eid for b in batches for eid in b.entity_ids]
    assert sorted(enumerated) == sorted(all_entity_ids)
    assert len(enumerated) == len(set(enumerated))
```

The second test is the important one. An off-by-one in a paging loop produces a
run that **completes** having silently scored fewer entities than exist — no
error, no failed batch, just a smaller number nobody checks.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/test_executor.py -k pages -v`
Expected: FAIL — `unbounded_calls == 1`

- [ ] **Step 3: Page the enumeration**

Read a page, extend the id list, stop when a page comes back short. Use a
constant with the existing env-override helper:

```python
_ENUMERATION_PAGE_SIZE = _positive_int_from_env("CHILI_SCORE_ENUMERATION_PAGE_SIZE", 1000)
```

Stop on `len(page) < limit`, not on `page == []` — otherwise a knowledge base
whose entity count is an exact multiple of the page size costs one extra query
every run.

The full id list is still held in memory to form batches. That is a smaller
claim than "streams" — the read is bounded per query, the accumulation is not.
Say so in the code comment rather than implying more.

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/pytest tests/analytics/ -v`

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/score_runs backend/tests/analytics
git commit -m "perf(score-runs): page through entity enumeration instead of one unbounded read"
```

---

### Task 3: Page the GNN snapshot read

**Files:**
- Modify: `backend/analytics/gnn/adapters/graph_repository_source.py`
- Test: `backend/tests/analytics/gnn/test_graph_repository_source.py`

The second unbounded caller. There is an existing 5000-node snapshot cap in the
GNN path — confirm where it is applied before changing anything. If the cap is
applied *after* the read, the unbounded query still runs and the cap only
bounds the compute.

- [ ] **Step 1: Establish where the cap actually applies**

Read the current code and write down which is true:

- (a) the cap bounds the read → paging is a modest improvement
- (b) the cap bounds only the compute → the read is genuinely unbounded and
  paging changes the failure mode on a large graph

Do not proceed until you know. The test you write depends on it.

- [ ] **Step 2: Write the failing test**

```python
def test_the_snapshot_source_never_issues_an_unbounded_read() -> None:
    repository = _CountingGraphRepository(entity_count=250)
    source = GraphRepositorySnapshotSource(repository)

    source.load_snapshot("kb-1")

    assert repository.unbounded_calls == 0


def test_the_snapshot_respects_the_node_cap_while_paging() -> None:
    """Paging must not accidentally lift the cap — that would turn a bounded
    O(n^2)/O(n^3) analytics step loose on an arbitrarily large graph."""
    ...
```

That second test matters more than the first. `analytics/gnn` has known
O(n²)/O(n³) steps inside the snapshot cap; a paging change that reads past the
cap converts a bounded computation into an unbounded one.

- [ ] **Step 3: Implement, preserving the cap**

Page until either the source is exhausted or the cap is reached, whichever comes
first. The cap wins.

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/pytest tests/analytics/gnn/ -v`

- [ ] **Step 5: Commit**

```bash
git add backend/analytics/gnn backend/tests/analytics/gnn
git commit -m "perf(gnn): page the snapshot read while preserving the node cap"
```

---

### Task 4: Give the alert WebSocket stream a producer

**Files:**
- Modify: `backend/api/routers/ws.py`, and whichever module publishes alerts
- Test: `backend/tests/api/test_ws_router.py`

This is G8. `AlertCreatedEvent` is documented as *"surfaced to real-time
WebSocket subscribers"* and is **constructed nowhere outside a test**. The hub
says so itself: *"does not subscribe to Redis Streams — the event bus bridge is
added in Epic 8."* The route accepts connections, applies severity filters, and
emits nothing.

**Decide the scope before writing code.** Two honest options:

- **(a) Build the bridge.** The API process subscribes to the event bus and
  fans out to hub subscribers. This is real work: a background consumer in the
  API process, its lifecycle tied to app startup/shutdown, and a decision about
  what happens with multiple API replicas (each would need its own subscription
  with a distinct consumer name, or subscribers see only the alerts their
  replica happened to consume).
- **(b) Retire the surface.** Delete the alert WebSocket route and
  `AlertCreatedEvent`, and let clients poll `/alerts`, which is durable and
  already works.

**Recommendation: (b), unless real-time alerting is a committed requirement.**
The durable alert feed already serves this data. A WebSocket that has never
emitted anything is not a feature being finished — it is a surface that has been
lying for its whole existence, and the multi-replica fan-out problem is a real
distributed-systems design task, not a wiring job.

If (b): delete the route, the hub's alert branch, `AlertCreatedEvent`, and its
codec entry; remove the `NOTIFICATION_ONLY_EVENT_TYPES` entry if Plan 2 Task 1
added one; check `chili_app/src/hooks/useWebSocket.ts` for callers (there are
none as of 2026-08-07, but verify).

If (a): the consumer must not block app startup, must not crash the API when
Redis is unavailable, and needs a test that a published `AlertCreatedEvent`
reaches a connected subscriber **through the bus**, not through a direct
`hub.broadcast` call — the existing tests all call `broadcast` directly, which
is exactly why the missing producer went unnoticed.

- [ ] **Step 1: Record the decision**

Write which option and why in the commit message. This is a product decision as
much as a technical one; do not make it silently.

- [ ] **Step 2–5: Implement, test, run gates, commit**

Steps depend on the option chosen. Either way, the coherence test from Plan 2
Task 1 (`every declared event type has a producer or is listed notification-only`)
must pass afterward without an allow-list entry that merely hides the problem.

---

### Task 5: Surface parked runs in the dashboard

**Files:**
- Modify: `chili_app/src/pages/DashboardPage.tsx`
- Test: `chili_app/src/pages/__tests__/DashboardPage.test.tsx`

This is G2. `RunTimeline` was fixed when `awaiting_approval` was added;
`DashboardPage` was not. Its `workflowCounts` tiles count queued/running/failed/
completed, so a parked run appears in none of them.

- [ ] **Step 1: Write the failing tests**

```tsx
it('counts a run awaiting approval', () => {
  renderDashboard({ workflows: [parkedRun, runningRun] })

  expect(screen.getByTestId('workflow-count-awaiting-approval')).toHaveTextContent('1')
})

it('reports awaiting approval as the primary state when nothing is running', () => {
  // A parked run is the thing an operator can act on; showing 'idle' hides
  // work that is waiting specifically for them.
  renderDashboard({ workflows: [parkedRun] })

  expect(screen.getByTestId('primary-workflow-state')).toHaveTextContent(/awaiting approval/i)
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd chili_app && npm run test:run -- DashboardPage`

- [ ] **Step 3: Implement**

Add the count tile, and give `primaryWorkflowState` an `awaiting_approval`
branch. Order it **after** `running` and `failed` but **before** `queued`: a
parked run needs a human, so it outranks work that is merely waiting on a
worker.

- [ ] **Step 4: Run the full frontend gates**

```bash
cd chili_app && npm run lint && npm run test:run && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add chili_app
git commit -m "feat(frontend): count and surface runs awaiting approval on the dashboard"
```

---

### Task 6: Live verification and docs

**Files:**
- Modify: `backend/tests/e2e/`, `docs/ledger/module-map.md`

- [ ] **Step 1: Verify the bounded reads against real data**

A paging bug is invisible on ten entities. Use the CMS demo data
(`make demo-cms`, or an existing seeded KB with a few thousand entities) and
assert the enumerated count equals the graph's actual entity count:

```bash
# entity count from the graph
docker exec chiliai-neo4j-1 cypher-shell -u neo4j -p "$NEO4J_PASSWORD" --format plain \
  "MATCH (n:Entity {knowledge_base_id:'<kb>'}) RETURN count(*)"
# then start a score run and compare total_entities
```

`total_entities` must equal that count exactly. Off-by-one paging produces a
run that completes having scored fewer entities than exist, with no error.

- [ ] **Step 2: Confirm the dashboard shows a parked run**

Requires Plan 1 for a run to park. If Plan 1 has not landed, park one by hand
(set a run to `awaiting_approval` in the store) and confirm the tile appears.
Say in the commit which method was used.

- [ ] **Step 3: Update the docs**

`module-map.md` under `analytics/score_runs/` says enumeration *"still
materialises the full entity list once"* — replace with what is true after Task
2, including the honest limit (bounded per query; the id list is still
accumulated in memory).

Record the Task 4 decision under the alerts/monitoring entry, whichever way it
went.

- [ ] **Step 4: Run the full gates**

```bash
cd backend && .venv/bin/pytest --cov -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .
cd ../tools && ../backend/.venv/bin/pyright
cd ../chili_app && npm run lint && npm run test:run && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add backend docs chili_app
git commit -m "test: verify bounded entity reads against real data volumes"
```

---

## Self-review notes

- **Spec coverage:** G6 (Tasks 1–3), G8 (Task 4), G2 (Task 5).
- **Task 4 is a decision, not a task.** It is written that way on purpose: the
  recommendation is to retire the surface, and an implementer should not build a
  multi-replica WebSocket fan-out because a plan step said "implement".
- **Task 3 Step 1 is a research step with no code.** The test to write depends
  on where the existing node cap applies, and guessing produces a test that
  passes while the unbounded read remains.
- **The riskiest change here is Task 2/3 paging**, not the visible ones. A
  dropped page produces a successful run over a subset — no error anywhere. That
  is why both tasks have a "covers every entity exactly once" test and Task 6
  checks against a real entity count.
