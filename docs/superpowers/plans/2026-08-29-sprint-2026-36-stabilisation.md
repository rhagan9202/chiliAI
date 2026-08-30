# Sprint 2026-36 — Stabilisation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the six defects sprint 2026-35 introduced, shipped, or left half-done — one of which is live on `prod`.

**Architecture:** No new subsystems. Three of the six exist because two adapters behind one protocol diverged and only the in-memory one was exercised, so the through-line is parity: every fix is proven against *both* adapters, parametrised, with the non-default one genuinely executing.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic, psycopg 3, redis-py, pytest, pyright strict.

**Spec:** `docs/superpowers/specs/2026-08-28-sprint-2026-36-stabilisation-design.md`

## Global Constraints

- `pyright` run **bare from `backend/`** must be clean — `tool.pyright.include` covers much of `tests/**`, so test code is strict-checked too. Per-file invocation misses include-scoped errors.
- `backend/.venv/bin/ruff check --no-cache .` clean (`--no-cache` required; the cache dir is not writable here).
- pytest coverage ≥ 85% per package.
- **Never point `DATABASE_URL` at the dev `chili` database.** Export `postgresql://chili:chili@localhost:5432/chili_test` or nothing. `tests/database/test_migrations.py` runs `alembic downgrade base` against it.
- Integration tests need Postgres and Redis: `docker compose -f docker-compose.dev.yaml up -d --wait postgres redis`.
- **Adapter parity is a test requirement, not a code requirement.** Any fix touching one adapter is tested against *both*, parametrised. A skipped half and a passing half are indistinguishable in a pytest summary line — assert the non-default adapter actually ran.
- **Every test is watched failing against the real defect first.** A test that fails because a method does not exist proves only that. This clause caught three tests in the previous sprint's plan that could not have gone RED.
- **A finding becomes a backlog story when you raise it, not at close-out.** Four Important findings were lost from the last sprint exactly that way.
- No `Any`; full annotations; follow surrounding file style.
- Do not run a full-repo suite; the controller runs it at close-out.
- Commit after every task, conventional-commit subjects.

## Findings from exploration that change the work

Read before task 1. Each contradicts something a reader would reasonably assume.

- **`records.18` is narrower than its story implies.** The story describes a correlation-scoped delete taking out earlier pages of a connector sync run. That was already fixed in 2026-35's final fix wave — `records/service.py` now calls `delete_records(keys=inserted_keys)`, scoped to the keys `persist` reported inserting. The *remaining* defect is only that `delete_records` and `discard_submission` are two separate transactions. Do not re-fix the scoping.
- **`delete_by_kb` is the shape to copy.** `records/adapters/postgres.py:141-152` already does two statements in one transaction with a single commit. Task 4 is making the rollback look like that.
- **The pagination divergence is NOT simply "unfiltered vs filtered".** Both stores scope their listing by knowledge base and status — the Redis ZSET is keyed per `(kb, status)` via `_listing_index_key`. The skew comes from Redis *skipping stale entries* (a ZSET id whose run no longer exists) so `page.items` can be shorter than the positions consumed, and from its own trailing `next_offset -= stale_count` compensation. **Do not take my word for the mechanism.** Task 1's first job is an empirical parity test that exposes the actual behaviour; derive the fix from what you observe.
- **The entitlement filter lives in the router, not either store.** `_can_access_workflow` runs after `list_workflows` returns, so neither store's `next_offset` accounts for it. That is why the router does its own arithmetic at all.
- **`monitoring`'s in-memory alert store validates but does not compare-and-set.** `in_memory.py:188` (`acknowledge`) and `:248` (`transition_status`) call `validate_alert_transition` and then write, with no guard and no lock — while the Postgres sibling now does CAS. `get_alert_feed_store` is `@lru_cache(maxsize=1)`, a process singleton shared across threadpool requests, so this is reachable.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `backend/api/routers/workflows.py` | Cursor arithmetic correct for both stores | 1 |
| `backend/monitoring/exceptions.py` | A dedicated lost-race exception | 2 |
| `backend/monitoring/adapters/postgres.py` | Raise the typed error instead of the generic one | 2 |
| `backend/monitoring/adapters/in_memory.py` | CAS + lock, matching Postgres | 2 |
| `backend/api/routers/alerts.py`, `backend/api/dependencies.py` | Convert a lost race to 409 | 2 |
| `backend/conversations/service.py` + both adapters | Guard the read-modify-write | 3 |
| `backend/records/service.py`, `backend/records/adapters/*` | One-transaction rollback | 4 |
| `backend/knowledgebases/protocols.py` + both adapters | Per-stage warning accounting | 5 |
| `backend/tests/e2e/stack_gate.py` + the three e2e suites | Gate every skip | 6 |

---

### Task 1 (`api.30`): Pagination is correct for both workflow-run stores

**Files:**
- Modify: `backend/api/routers/workflows.py:50-84`
- Test: `backend/tests/api/test_workflows_router.py`

**Interfaces:**
- Produces: no signature change. `_list_accessible_workflows` returns a cursor valid under both stores.

> This is the only task fixing a defect currently live on `prod`.

- [ ] **Step 1: Write the parity test first — it must fail against the Redis store and pass against in-memory**

The point is to expose the divergence, not to assume it. Parametrise over both stores, seed runs where some are denied by entitlement so the mid-page-fill branch is taken, and assert the *union of two consecutive pages contains each accessible run exactly once*.

```python
@pytest.mark.parametrize("store_name", ["in_memory", "redis"])
def test_a_run_appears_exactly_once_across_consecutive_pages(store_name: str) -> None:
    """The router's cursor must mean the same thing to both stores.

    `_list_accessible_workflows` returns `scan_offset + consumed`, counting items
    in the page the store returned. Whether that is a valid offset *for that
    store* is the thing under test -- the entitlement filter runs in the router,
    so neither store's own next_offset accounts for it.
    """
    store = _make_store(store_name, runs=_mixed_entitlement_runs(count=10))
    client = _client(store=store, user=_entitled_to("kb-1"))

    first = client.get("/workflows?limit=3").json()
    second = client.get(f"/workflows?limit=3&offset={first['next_offset']}").json()

    seen = [item["workflow_id"] for item in first["items"] + second["items"]]
    assert len(seen) == len(set(seen)), f"a run was returned twice: {seen}"
    assert seen == sorted(seen, key=_expected_order), f"a run was skipped: {seen}"
```

- [ ] **Step 2: Run it and record what actually happens under each store**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/api/test_workflows_router.py -k appears_exactly_once -v`

Expected: the `in_memory` case passes, the `redis` case fails. **Capture the exact failure verbatim** — a duplicate or a skip, and which run. That output determines the fix; do not proceed on the mechanism described in this plan without confirming it.

- [ ] **Step 3: Decide where the fix belongs, and say why in your report**

Two defensible options. Pick one deliberately:

- **(a) Make the stores agree** — give `WorkflowRunPage` a cursor whose meaning is defined by the protocol rather than by each adapter's internals, so the router can add to it safely.
- **(b) Stop the router doing arithmetic on a store-owned cursor** — have the router ask the store to resume after a specific run rather than at a computed offset.

(b) is structurally cleaner and removes the whole class of bug; (a) is smaller. Choose based on what Step 2 shows, and record the reasoning.

- [ ] **Step 4: Implement, then re-run both parametrisations**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/api/test_workflows_router.py -v`

Expected: PASS for both stores. Confirm the pre-existing edge cases still hold — limit filled exactly at a page boundary, page exhausted without filling the limit, no more pages, a page with zero accessible runs, and `limit=0` (routed around this function entirely by the `if limit == 0:` branch).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/workflows.py backend/tests/api/test_workflows_router.py
git commit -m "fix(api): make entitlement-filtered pagination correct for both run stores"
```

---

### Task 2 (`monitoring.22`): Signal a lost write race instead of returning 500

**Files:**
- Create: exception in `backend/monitoring/exceptions.py`
- Modify: `backend/monitoring/adapters/postgres.py:398,489`, `backend/monitoring/adapters/in_memory.py:188,248`, `backend/api/routers/alerts.py`, `backend/api/dependencies.py`
- Test: `backend/tests/monitoring/`, `backend/tests/api/test_alerts_router.py`

**Interfaces:**
- Produces: `AlertConcurrentModificationError(MonitoringError)` — the monitoring sibling of `CaseConcurrentModificationError` (`cases/exceptions.py:34`). Task 3 consumes the contract this task sets.

> This is the sprint's design story. The codebase currently holds three answers to "what happens when you lose a write race" and none reaches a caller as a 409.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_lost_alert_race_is_typed_not_a_generic_source_error(
    database_url: str,
) -> None:
    """MonitoringSourceError means "the database failed". Overloading it for a
    lost race means no caller can tell a benign retry-me from an outage, which
    is why the bulk endpoint aborts the whole batch on one.
    """
    ...
    with pytest.raises(AlertConcurrentModificationError):
        _lose_a_race(store)


def test_the_in_memory_alert_store_also_loses_the_race_loudly() -> None:
    """Postgres got compare-and-set; the in-memory sibling still validates and
    writes with no guard and no lock. get_alert_feed_store is an lru_cache(1)
    process singleton shared across threadpool requests, so this is reachable.
    Deliberately widen the window rather than hoping for a GIL interleave.
    """
    ...


def test_a_lost_race_surfaces_as_409_not_500() -> None:
    """The exception's own text says "retry the transition". Today the caller
    gets an opaque 500 and cannot act on it."""
    response = client.post("/alerts/alert-1/status", json={...})
    assert response.status_code == 409
```

- [ ] **Step 2: Run them and watch them fail**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/monitoring/ tests/api/test_alerts_router.py -k "lost_race or concurrent" -v`

Expected: FAIL — the typed exception does not exist, the in-memory store silently accepts both writes, and the route returns 500.

- [ ] **Step 3: Add the typed exception**

```python
class AlertConcurrentModificationError(MonitoringError):
    """Raised when an alert changed between the caller's read and its write.

    Distinct from ``MonitoringSourceError``, which means the database itself
    failed. A caller can safely retry this one; it must not retry that one.
    """
```

- [ ] **Step 4: Raise it from both adapters, and give the in-memory store a real guard**

Postgres: replace the two `MonitoringSourceError("...retry the transition.")` raises. In-memory: hold a `threading.Lock` across the read-validate-write in both `acknowledge` and `transition_status`, and raise the same error when the observed status changed — mirroring `InMemoryCaseRepository.update`, which took exactly this fix in 2026-35.

- [ ] **Step 5: Convert it to a 409 at the gateway**

Map it in the single-alert routes and in the bulk builder. For bulk, decide deliberately whether a lost race is now a per-row skip (safe — nothing committed on that branch) rather than a batch abort, and say which you chose. The batch abort exists only because the error was untypeable.

- [ ] **Step 6: Run and commit**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/monitoring/ tests/api/test_alerts_router.py -v`

```bash
git add backend/monitoring backend/api backend/tests
git commit -m "fix(monitoring): type the lost write race and surface it as 409"
```

- [ ] **Step 7: Record the contract**

Write the decision into `backend/monitoring/README.md`: what a lost race raises, what it means to a caller, and that `cases` and `conversations` follow the same contract. Task 3 depends on this being written down.

---

### Task 3 (`conversations.06`): Guard the conversation read-modify-write

**Files:**
- Modify: `backend/conversations/service.py` (`append_messages`), `backend/conversations/adapters/postgres.py:34-42,84-91`, `backend/conversations/adapters/in_memory.py`
- Test: `backend/tests/conversations/`

**Interfaces:**
- Consumes: the lost-race contract Task 2 establishes and documents. **Do not invent a fourth answer** — read `backend/monitoring/README.md` first.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.parametrize("repository_name", ["in_memory", "postgres"])
def test_two_concurrent_turns_both_survive(repository_name: str) -> None:
    """append_messages is get -> model_copy -> save, and the Postgres upsert is
    ON CONFLICT ... SET messages = EXCLUDED.messages -- a full overwrite. Two
    turns landing at once both read the same list and the second write discards
    the first, with a 200 returned to the analyst whose message vanished.

    Barrier-synchronised so both reads land before either write; a sequential
    test cannot reproduce this.
    """
    repository = _make_repository(repository_name)
    service = create_conversation_service(repository)
    conversation = service.create(_new_conversation())

    barrier = threading.Barrier(2)

    def append(text: str) -> None:
        barrier.wait(timeout=5)
        service.append_messages(conversation.id, [_message(text)])

    _run_concurrently(append, ["from-analyst-a", "from-analyst-b"])

    stored = repository.get(conversation.id)
    assert stored is not None
    texts = {m.content for m in stored.messages}
    assert {"from-analyst-a", "from-analyst-b"} <= texts, f"a turn was lost: {texts}"
```

- [ ] **Step 2: Run it and watch a turn disappear**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/conversations/ -k concurrent_turns -v`

Expected: FAIL on both adapters, with one message missing and **no exception raised** — the silent loss is the defect.

- [ ] **Step 3: Guard the write**

`updated_at` is already service-owned (2026-35 Task 13), so it is available as a compare-and-set token exactly as `cases` uses it. Add the guard to the Postgres upsert's `WHERE`, give the in-memory adapter a `threading.Lock` across its compare-and-write, and raise whatever Task 2's contract specifies.

- [ ] **Step 4: Run and commit**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/conversations/ -v`

```bash
git add backend/conversations backend/tests/conversations
git commit -m "fix(conversations): guard the append read-modify-write against concurrent turns"
```

---

### Task 4 (`records.18`): Make the rollback one transaction and stop masking the publish error

**Files:**
- Modify: `backend/records/service.py` (rollback block, ~line 118-132), `backend/records/adapters/postgres.py`, `backend/records/adapters/in_memory.py`, `backend/records/adapters/protocols.py`
- Test: `backend/tests/records/test_service.py`, `backend/tests/records/test_postgres_store.py`

**Interfaces:**
- Produces: one rollback call that does both the row deletion and the hash discard atomically.

> The row-scoping is **already correct** — `delete_records(keys=inserted_keys)` landed in 2026-35's fix wave. Do not re-fix it. This task is only about atomicity and error masking.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_failure_between_the_two_rollback_steps_does_not_strand_the_client() -> None:
    """delete_records and discard_submission commit separately. A failure
    between them leaves rows deleted and the hash retained, so the client's
    retry returns duplicate=True with zero rows -- forever, since nothing will
    ever publish an event for rows that no longer exist.
    """
    store = _StoreFailingAfterDelete()
    service = create_records_service(store, event_bus=_PublishAlwaysFails(), ...)

    with pytest.raises(Exception):
        _push(service, rows)

    receipt = _push(service, rows)          # the client's retry
    assert receipt.duplicate is False, "the retry was refused as a duplicate"
    assert receipt.accepted_count == len(rows)


def test_the_publish_error_is_not_replaced_by_a_storage_error() -> None:
    """The bare `raise` that re-surfaces the publish failure only runs if both
    rollback calls succeed. Otherwise a Redis outage is reported as
    "Record storage failure", pointing the operator at the wrong subsystem.
    """
    with pytest.raises(RuntimeError, match="event bus"):
        _push(_service_whose_rollback_also_fails(), rows)
```

- [ ] **Step 2: Run and watch them fail**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/records/ -k "rollback_steps or publish_error" -v`

Expected: FAIL — the retry comes back `duplicate=True`, and the surfaced error names storage rather than the event bus.

- [ ] **Step 3: Combine into one transaction**

Copy the shape `delete_by_kb` already uses (`records/adapters/postgres.py:141-152`): two statements, one connection, one commit.

```python
    def rollback_submission(
        self,
        *,
        knowledge_base_id: str,
        keys: list[tuple[str, str]],
        submission_hash: str,
    ) -> int:
        """Delete the given rows and forget the submission hash atomically.

        Two separate transactions could leave rows deleted with the hash
        retained, which makes the client's identical retry a permanent no-op:
        duplicate=True, zero rows, no event.
        """
        try:
            with self._provider.connection() as conn:
                cursor = conn.execute(_DELETE_RECORDS_SQL, (knowledge_base_id, keys))
                conn.execute(_DISCARD_SUBMISSION_SQL, (knowledge_base_id, submission_hash))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise RecordPersistenceError("Failed to roll back the submission.") from exc
```

Add it to the protocol and the in-memory adapter with identical semantics.

- [ ] **Step 4: Let the publish error survive a failed rollback**

In `service.py`, wrap the rollback so its own failure is logged and the original publish exception still propagates. The operator needs to know Redis was down, not that storage was.

- [ ] **Step 5: Run and commit**

Run: `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/records/ -v` and the same with `-m integration`.

```bash
git add backend/records backend/tests/records
git commit -m "fix(records): make the publish-failure rollback atomic and preserve the original error"
```

---

### Task 5 (`agent.22`): Per-stage document warning accounting

**Files:**
- Modify: `backend/knowledgebases/protocols.py`, `backend/knowledgebases/adapters/in_memory.py`, `backend/knowledgebases/adapters/object_store.py`, `backend/agent/coordinator.py:2045`
- Test: `backend/tests/knowledgebases/test_document_warnings.py`, `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Produces: an absolute setter keyed by `(document, stage)`, with the document total derived as the sum across stages.

> There is **no Postgres adapter** for `KnowledgeBaseRepository` — only `in_memory.py` and `object_store.py`. Both are real and both must match.

- [ ] **Step 1: Write the failing test**

```python
def test_replaying_the_extract_stage_does_not_inflate_the_total() -> None:
    """2026-35 fixed the parse stage with an absolute setter. The extract stage
    (handle_entities_extracted, coordinator.py:2045) still does an additive
    record_document_warnings, so a retry still inflates.

    It was left deliberately: the two stages accumulate into one total by
    design, so switching it to the existing absolute setter would make extract
    overwrite parse -- trading a replay bug for a data-loss bug. Per-stage
    accounting is what closes both.
    """
    repository = _seeded()
    _record_stage(repository, stage="parse", count=2, reasons=["truncated table"])

    _record_stage(repository, stage="extract", count=3, reasons=["unknown type"])
    _record_stage(repository, stage="extract", count=3, reasons=["unknown type"])  # replay

    document = repository.get_document("kb-1", "doc-1")
    assert document.warning_count == 5           # 2 parse + 3 extract, not 8
    assert document.warning_reasons == ["truncated table", "unknown type"]
```

- [ ] **Step 2: Run and watch the inflation**

Run: `cd backend && .venv/bin/pytest tests/knowledgebases/ tests/agent/ -k replaying_the_extract -v`

Expected: FAIL with `warning_count == 8` and duplicated reasons.

- [ ] **Step 3: Add per-stage accounting to the protocol and both adapters**

```python
    def set_stage_document_warnings(
        self,
        knowledge_base_id: str,
        document_id: str,
        *,
        stage: str,
        count: int,
        reasons: list[str],
    ) -> None:
        """Set one stage's contribution absolutely; the document total is the
        sum across stages.

        Absolute per stage rather than additive overall, so replaying a handler
        converges instead of accumulating, while a later stage cannot overwrite
        an earlier stage's contribution.
        """
```

Keep the shared reasons cap and the same guard order in both adapters — document absent, knowledge base absent, empty reasons — since divergence there is the defect class this sprint exists to close.

- [ ] **Step 4: Switch both call sites onto it**

`handle_documents_parsed` moves from `set_document_warnings` to the stage-keyed setter with `stage="parse"`; `handle_entities_extracted` (coordinator.py:2045) moves off the additive `record_document_warnings` with `stage="extract"`. Resolve the `set_document_warnings` / `record_document_warnings` return-shape asymmetry while you are here, and remove whichever is left with no callers so the additive path cannot be reintroduced.

- [ ] **Step 5: Run and commit**

Run: `cd backend && .venv/bin/pytest tests/knowledgebases/ tests/agent/ -v`

```bash
git add backend/knowledgebases backend/agent backend/tests
git commit -m "fix(knowledgebases): account for document warnings per stage so replay cannot inflate"
```

- [ ] **Step 6: Update the module docs**

`backend/knowledgebases/README.md` and `backend/agent/README.md` record the per-stage model. `docs/architecture.md` currently describes the split between the absolute parse-stage write and the additive extract-stage one — that sentence becomes wrong.

---

### Task 6 (`cicd.22`): Gate every live-stack skip, not just the base-URL probe

**Files:**
- Modify: `backend/tests/e2e/stack_gate.py`, `backend/tests/e2e/test_approval_and_replay_flow.py`, `test_connector_sync_flow.py`, `test_workflow_run_flow.py`
- Test: `backend/tests/e2e/test_stack_gate.py`

**Interfaces:**
- Produces: the gate is callable for any skip reason, not only the base-URL probe.

- [ ] **Step 1: Write the failing test**

```python
def test_a_non_probe_skip_also_fails_when_the_stack_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHILI_E2E_REQUIRE_STACK gates only resolve_stack today. Every other
    live-stack skip -- a missing imports directory, a failed docker exec, and
    "No completed score run available to replay" -- still skips silently.

    That last one fires in exactly the case where the feature under test did not
    work, so a broken-but-listening stack still produces a green run.
    """
    monkeypatch.setenv("CHILI_E2E_REQUIRE_STACK", "1")

    with pytest.raises(Failed):
        require_stack_condition(False, "No completed score run available to replay.")
```

- [ ] **Step 2: Run and watch it skip instead of fail**

Run: `cd backend && .venv/bin/pytest tests/e2e/test_stack_gate.py -k non_probe_skip -v`

Expected: FAIL — `require_stack_condition` does not exist.

- [ ] **Step 3: Expose the gate**

```python
def require_stack_condition(condition: bool, reason: str) -> None:
    """Skip, or fail when the stack is required.

    ``_unavailable`` was reachable only from ``resolve_stack``, so every other
    live-stack skip stayed silent under CHILI_E2E_REQUIRE_STACK -- including one
    that fires precisely when the feature under test did not work.
    """
    if condition:
        return
    _unavailable(reason)
```

- [ ] **Step 4: Route every `pytest.skip` in `tests/e2e/` through it**

Find them: `grep -rn 'pytest.skip' backend/tests/e2e/`. The score-run replay skip at `test_approval_and_replay_flow.py:262` is the one that matters most.

- [ ] **Step 5: Run and commit**

Run: `cd backend && .venv/bin/pytest tests/e2e/ -v` and again with `CHILI_E2E_REQUIRE_STACK=1` to confirm the skips become failures.

```bash
git add backend/tests/e2e
git commit -m "test(e2e): gate every live-stack skip behind CHILI_E2E_REQUIRE_STACK"
```

---

## Sprint close-out

- [ ] **Run every gate**

```bash
cd backend && .venv/bin/pyright
.venv/bin/ruff check --no-cache .
DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov -q
cd .. && make check
```

- [ ] **Run the CI backend job to completion at least once.** It has never finished: the wait step it depended on could only time out until it was fixed, and its `DATABASE_URL` was only repointed at `chili_test` in `f265a6ef`. Until it runs, "CI is green" is unevidenced.

- [ ] **Verify against a running stack** if the Neo4j port conflict on the development host is resolved. Still outstanding from 2026-35: `_SizeLimitedPushRoute`'s keep-alive behaviour after aborting mid-`receive()` under real uvicorn, and the end-to-end exercise of each finding 2026-35 closed.

- [ ] **Write `docs/project/planning/sprints/2026-36.md`** in the format of `2026-35.md`. Do not defer this to a later session — the 2026-35 doc went unwritten for exactly that reason.
