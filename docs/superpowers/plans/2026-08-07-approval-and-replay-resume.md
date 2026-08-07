# Approval and Replay Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make three accepted-but-never-executed paths actually execute — a workflow run parked on approval, a replayed score run, and a connector sync run that stalls.

**Architecture:** No new machinery. Each gap is a missing publish or a missing sweep on top of engines that already work: the approval endpoint republishes `workflow.step.queued`, `replay_failed_batches` publishes `score.batch.queued` the way `start_run` already does, and a `ConnectorSyncReconciler` mirrors `ScoreRunReconciler`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, psycopg, Alembic, Redis Streams, pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-execution-gap-closure-design.md` §2 Tier 1, §3 D1

**Depends on:** nothing. All three executors are on `prod`.

## Global Constraints

- Python 3.12. Full type annotations; **no `Any`**. Bare `backend/.venv/bin/pyright` must report 0 errors (it covers `tests/**` too).
- `backend/.venv/bin/ruff check --no-cache .` must pass.
- Tests run from `backend/`. **Never use a cwd-relative path in a test** — use `Path(__file__).resolve().parents[N]`, and count the levels for the file you are in.
- Never point `DATABASE_URL` at the dev `chili` database; `tests/conftest.py` defaults to `chili_test`.
- Coverage ≥ 85% per package.
- Executors **raise** only for conditions a retry could fix; conditions that cannot succeed on retry fail the run with the reason recorded.
- Any frontend-consumed Pydantic change requires OpenAPI export + `npm run codegen:api` + **`npm run build`** (see spec §4.5).

## Verification Doctrine (inherited — spec §4)

Every task in this plan obeys these. They are not optional polish; each one
corresponds to a defect that shipped.

1. **Break the guard to prove it works.** Where a step adds a coherence or
   registration test, it states the mutation that must turn it red, and you run
   that mutation.
2. **Assert the projection, not the record.** Where a state is user-visible,
   assert what an HTTP client receives.
3. **Verify the sibling path.** This plan exists partly because `start_run` was
   verified and `replay` was not.
4. **Live stack before done.** Task 7 is not optional.

## File Structure

| File | Responsibility |
|---|---|
| `backend/api/contracts.py` | `WorkflowStepApprovalRequest`, `WorkflowStepDecisionResponse` |
| `backend/api/routers/workflows.py` | `POST .../steps/{step_id}/approve` and `/reject` |
| `backend/agent/service.py` | `approve_step` / `reject_step` on the agent service |
| `backend/analytics/score_runs/service.py` | publish `score.batch.queued` on replay |
| `backend/connectors/reconciler.py` | `ConnectorSyncReconciler` |
| `backend/connectors/repository.py` | `list_stale_runs` on the protocol |
| `backend/connectors/adapters/{in_memory,postgres}.py` | `list_stale_runs` implementations |
| `backend/agent/coordinator.py` | drive the connector reconciler on the existing tick |

---

### Task 1: `list_stale_runs` on the connector repository

**Files:**
- Modify: `backend/connectors/repository.py`, `backend/connectors/adapters/in_memory.py`, `backend/connectors/adapters/postgres.py`
- Test: `backend/tests/connectors/test_in_memory.py`, `backend/tests/connectors/test_postgres.py`

**Interfaces:**
- Produces: `list_stale_runs(*, statuses: tuple[ConnectorSyncStatus, ...], updated_before: datetime, limit: int = 1000) -> list[ConnectorSyncRun]`

Mirror `ScoreRunRepositoryProtocol.list_stale_runs` exactly — same name, same
keyword-only shape, same "maintenance scan across every KB" docstring reasoning.
Two reconcilers with different scan signatures is how the third one gets written
wrong.

- [ ] **Step 1: Write the failing tests**

```python
def test_list_stale_runs_returns_only_old_non_terminal_runs() -> None:
    repository = InMemoryConnectorRepository()
    repository.save_definition(_definition_payload())
    fresh = repository.create_run(_run_create())
    stale = repository.create_run(_run_create())
    old = datetime(2026, 8, 1, tzinfo=timezone.utc)
    repository.update_run(stale.run_id, ConnectorSyncRunUpdate(status="running"))
    # Force the stale run's updated_at back; see Step 3 note on why the
    # in-memory adapter needs a seam for this.
    repository.set_updated_at_for_test(stale.run_id, old)

    found = repository.list_stale_runs(
        statuses=("queued", "running"),
        updated_before=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )

    assert [run.run_id for run in found] == [stale.run_id]
    assert fresh.run_id not in [run.run_id for run in found]


def test_list_stale_runs_never_returns_a_terminal_run() -> None:
    """Reaching a terminal state is what makes a run immune."""
    repository = InMemoryConnectorRepository()
    repository.save_definition(_definition_payload())
    run = repository.create_run(_run_create())
    repository.update_run(run.run_id, ConnectorSyncRunUpdate(status="completed"))
    repository.set_updated_at_for_test(run.run_id, datetime(2026, 8, 1, tzinfo=timezone.utc))

    assert repository.list_stale_runs(
        statuses=("queued", "running"),
        updated_before=datetime(2026, 8, 5, tzinfo=timezone.utc),
    ) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/connectors/test_in_memory.py -k stale -v`
Expected: FAIL — `AttributeError: 'InMemoryConnectorRepository' object has no attribute 'list_stale_runs'`

- [ ] **Step 3: Implement on the protocol and both adapters**

Protocol (`connectors/repository.py`), mirroring the score-run docstring:

```python
    def list_stale_runs(
        self,
        *,
        statuses: tuple[ConnectorSyncStatus, ...],
        updated_before: datetime,
        limit: int = 1000,
    ) -> list[ConnectorSyncRun]:
        """Runs in ``statuses`` not updated since ``updated_before``, any KB.

        Deliberately not `list_runs` with an optional filter: this is a
        maintenance scan across every knowledge base, and conflating the two
        makes it easy to run an unscoped query on the analyst-facing path.
        """
        ...
```

Postgres — the index `ix_connector_sync_runs_connector_status` is
`(connector_id, status, started_at DESC)`, which does **not** serve a scan by
`(status, updated_at)`. Add one:

```sql
CREATE INDEX IF NOT EXISTS ix_connector_sync_runs_status_updated
ON connector_sync_runs (status, updated_at)
```

This needs a new migration `0026_connector_sync_stale_index.py`
(`down_revision = "0025_connectors"`). Do **not** edit `0025`; it is merged.

In-memory needs `set_updated_at_for_test` because `update_run` always stamps
`updated_at = utc_now()`, so a test cannot age a run through the public API.
Name it `_for_test` and document that it exists solely so the reconciler is
testable without sleeping.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/connectors/ -v`
Expected: PASS

- [ ] **Step 5: Regenerate the schema snapshot**

Run: `make migrate-snapshot` from the repo root, then confirm
`git diff backend/database/migrations/snapshots/head.sql` shows only the new
index. CI's migrations job fails on drift.

- [ ] **Step 6: Commit**

```bash
git add backend/connectors backend/tests/connectors backend/database/migrations
git commit -m "feat(connectors): add list_stale_runs and the index that serves it"
```

---

### Task 2: `ConnectorSyncReconciler`

**Files:**
- Create: `backend/connectors/reconciler.py`
- Test: `backend/tests/connectors/test_reconciler.py`

**Interfaces:**
- Consumes: `list_stale_runs` (Task 1).
- Produces: `ConnectorSyncReconciler(repository, *, clock=utc_now).reconcile_stale_runs(*, max_age_seconds: int, batch_size: int = 1000) -> int`

Copy the structure of `analytics/score_runs/reconciler.py`, including its
re-read-before-write: a page may have landed between the scan and the update, in
which case the run is progressing and must be left alone.

- [ ] **Step 1: Write the failing tests**

```python
def test_reconciles_a_run_that_stopped_progressing() -> None:
    repository, run = _stale_run(status="running")
    reconciler = ConnectorSyncReconciler(repository, clock=lambda: NOW)

    assert reconciler.reconcile_stale_runs(max_age_seconds=3600) == 1

    reconciled = repository.get_run(run.run_id)
    assert reconciled is not None
    assert reconciled.status == "failed"
    assert reconciled.error_message == "stale_connector_sync_reconciled"


def test_leaves_a_run_that_progressed_between_scan_and_write() -> None:
    """The re-read is the point: a page landing mid-sweep must not be failed."""
    repository, run = _stale_run(status="running")
    reconciler = ConnectorSyncReconciler(repository, clock=lambda: NOW)
    repository.on_next_get_run(
        lambda: repository.update_run(
            run.run_id, ConnectorSyncRunUpdate(source_cursor="a.csv:10")
        )
    )

    assert reconciler.reconcile_stale_runs(max_age_seconds=3600) == 0


def test_rejects_a_non_positive_max_age() -> None:
    repository, _ = _stale_run(status="running")
    with pytest.raises(ValueError, match="max_age_seconds"):
        ConnectorSyncReconciler(repository).reconcile_stale_runs(max_age_seconds=0)
```

If wiring `on_next_get_run` into the in-memory adapter is more machinery than
it is worth, achieve the same by subclassing `InMemoryConnectorRepository` in
the test file and overriding `get_run` to mutate on first call. Do not skip the
test — "the sweep failed a run that was actually working" is the failure mode
that makes operators distrust reconcilers.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/connectors/test_reconciler.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the reconciler**

```python
_STALE_CANDIDATE_STATUSES: tuple[ConnectorSyncStatus, ...] = ("queued", "running")
_STALE_REASON = "stale_connector_sync_reconciled"
```

Mark the run `failed` with `error_message=_STALE_REASON` and log a warning
carrying `run_id`, `connector_id` and the last `updated_at`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/connectors/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/connectors/reconciler.py backend/tests/connectors/test_reconciler.py
git commit -m "feat(connectors): fail sync runs that stop progressing"
```

---

### Task 3: Drive the connector reconciler from the worker tick

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_coordinator.py`

**Interfaces:**
- Consumes: `ConnectorSyncReconciler` (Task 2), `deps.connector_repository` (already on `WorkerDependencies`).

- [ ] **Step 1: Write the failing test**

A guard, not a behavioural test — the behaviour is Task 2's. This asserts the
reconciler is *reached*, which is the thing that has gone wrong repeatedly:

```python
def test_the_worker_reconciles_every_run_type_that_can_stall() -> None:
    """Each chained executor advances by enqueueing its own successor, so one
    lost event stalls a run with no error and no terminal state. Every such
    run type needs a sweep, and this fails when a new one is added without."""
    source = (_BACKEND_DIR / "agent" / "coordinator.py").read_text(encoding="utf-8")
    tick = source.split("should_reconcile_workflows")[1].split("# Domain hot-swap")[0]

    for reconciler in (
        "workflow_tracker.reconcile_stale_runs",
        "ScoreRunReconciler",
        "ConnectorSyncReconciler",
    ):
        assert reconciler in tick, f"{reconciler} is never driven by the worker tick"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/agent/test_coordinator.py -k reconciles_every -v`
Expected: FAIL — `ConnectorSyncReconciler is never driven by the worker tick`

- [ ] **Step 3: Add it to the tick**

Inside the existing `if should_reconcile_workflows:` block, next to the
score-run sweep, guarded on `deps.connector_repository is not None`, using the
same `max_age_seconds=stale_workflow_max_age_seconds`. One tick, one cutoff —
three sweeps that disagree about staleness would be worse than none.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/agent/ -v`
Expected: PASS

- [ ] **Step 5: Prove the guard can fail**

Delete the `ConnectorSyncReconciler` block, re-run the test from Step 1, confirm
it is red, then restore. A guard that has never been seen red is not known to
work (spec §4.1).

- [ ] **Step 6: Commit**

```bash
git add backend/agent/coordinator.py backend/tests/agent/test_coordinator.py
git commit -m "feat(agent): sweep stale connector sync runs on the reconciliation tick"
```

---

### Task 4: Publish work events when replaying score batches

**Files:**
- Modify: `backend/analytics/score_runs/service.py`
- Test: `backend/tests/analytics/score_runs/test_service.py`

**Interfaces:**
- Consumes: `ScoreBatchQueuedEvent` (exists).
- Produces: no signature change — `replay_failed_batches` gains a publish.

This is G5. `start_run` publishes `ScoreRunQueuedEvent` or `ScoreBatchQueuedEvent`
for the first batch; `replay_failed_batches` publishes only
`ScoreRunStatusChangedEvent`, which is a notification the worker does not
consume. The replayed run is inert.

- [ ] **Step 1: Write the failing tests**

```python
def test_replaying_failed_batches_enqueues_the_first_replayed_batch() -> None:
    """Without this the replayed run is durable and completely inert.

    `_publish_status` emits ScoreRunStatusChangedEvent, which is a notification
    — the worker does not subscribe to it. Live-confirmed 2026-08-07: a
    replayed run stayed `queued` with scored=0 indefinitely.
    """
    service, repository, event_bus = _service_with_bus()
    original = _run_with_failed_batches(repository, count=2)

    result = service.replay_failed_batches(original.id, requested_by="operator-1")

    queued = [e for e in event_bus.published_events if isinstance(e, ScoreBatchQueuedEvent)]
    assert len(queued) == 1
    assert queued[0].run_id == result.run.id
    assert queued[0].batch_number == result.batches[0].batch_number


def test_an_idempotent_replay_does_not_enqueue_a_second_time() -> None:
    service, repository, event_bus = _service_with_bus()
    original = _run_with_failed_batches(repository, count=1)

    first = service.replay_failed_batches(original.id, requested_by="o", idempotency_key="k")
    second = service.replay_failed_batches(original.id, requested_by="o", idempotency_key="k")

    queued = [e for e in event_bus.published_events if isinstance(e, ScoreBatchQueuedEvent)]
    assert second.run.id == first.run.id
    assert len(queued) == 1


def test_replay_without_an_event_bus_still_creates_the_run() -> None:
    """In-process callers and unit tests may have no bus."""
    service, repository, _ = _service_with_bus(event_bus=None)
    original = _run_with_failed_batches(repository, count=1)

    assert service.replay_failed_batches(original.id, requested_by="o").created is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/analytics/score_runs/test_service.py -k replay -v`
Expected: FAIL — zero `ScoreBatchQueuedEvent` published

- [ ] **Step 3: Publish the first replayed batch**

After `self._publish_status(run)` and before the return, mirroring the branch
`start_run` already uses:

```python
        if self._event_bus is not None and replay_batches:
            # Start the chain. The executor enqueues batch N+1 from batch N, so
            # without this first event the replayed run is durable and inert —
            # queued forever, with nothing to explain why.
            self._event_bus.publish(
                ScoreBatchQueuedEvent(
                    correlation_id=run.id,
                    knowledge_base_id=run.knowledge_base_id,
                    run_id=run.id,
                    batch_id=replay_batches[0].id,
                    batch_number=replay_batches[0].batch_number,
                )
            )
```

Publish **only the first** batch, not all of them: the executor chains its own
successor, and publishing every batch would run them concurrently, defeating the
sequencing the chain exists to provide.

- [ ] **Step 4: Enumerate and verify the sibling paths (spec §4.3)**

G5 exists because a sibling entry point went unverified. Before continuing, list
every public method on `ScoreRunService` that creates or resumes work, and for
each confirm it publishes a work event or is deliberately notification-only.
Record the list in the commit message. At minimum: `start_run`,
`replay_failed_batches`, `cancel_run`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/analytics/ tests/api/test_score_runs_router.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/analytics/score_runs backend/tests/analytics
git commit -m "fix(score-runs): enqueue the first replayed batch so a replay actually executes"
```

---

### Task 5: Approve and reject a parked workflow step

**Files:**
- Modify: `backend/agent/service.py`, `backend/api/contracts.py`, `backend/api/routers/workflows.py`
- Test: `backend/tests/agent/test_service.py`, `backend/tests/api/test_workflows_router.py`

**Interfaces:**
- Produces: `AgentService.approve_step(workflow_id, step_id, *, actor_user_id, actor_roles) -> WorkflowRun` and `reject_step(..., reason: str) -> WorkflowRun`; routes `POST /workflows/{workflow_id}/steps/{step_id}/approve` and `/reject`.

This is G1, and it must fix **both** ends. Writing the approval metadata alone
does nothing: the parking event was acked, so no event exists to resume from.

- [ ] **Step 1: Write the failing tests**

```python
def test_approving_a_step_republishes_its_queued_event() -> None:
    """Both ends or neither. The parking event was acked, so recording the
    approval without republishing leaves the run just as stuck."""
    service, store, event_bus = _service_with_bus()
    run = _parked_run(store, step_id="gate")

    service.approve_step(run.workflow_id, "gate", actor_user_id="supervisor-1",
                         actor_roles=["supervisor"])

    queued = [e for e in event_bus.published_events if isinstance(e, WorkflowStepQueuedEvent)]
    assert [e.step_id for e in queued] == ["gate"]


def test_approving_records_who_approved_and_when() -> None:
    service, store, _ = _service_with_bus()
    run = _parked_run(store, step_id="gate")

    service.approve_step(run.workflow_id, "gate", actor_user_id="supervisor-1",
                         actor_roles=["supervisor"])

    updated = store.get_run(run.workflow_id)
    assert updated.metadata["approved.gate"] == "supervisor-1"
    assert updated.status is WorkflowRunStatus.QUEUED   # released from the gate


def test_the_requester_cannot_approve_their_own_run() -> None:
    """A gate an actor can satisfy for their own run is not a gate."""
    service, store, _ = _service_with_bus()
    run = _parked_run(store, step_id="gate", actor_user_id="analyst-1")

    with pytest.raises(WorkflowApprovalError, match="own"):
        service.approve_step(run.workflow_id, "gate", actor_user_id="analyst-1",
                             actor_roles=["supervisor"])


def test_approving_a_run_that_is_not_parked_is_rejected() -> None:
    service, store, _ = _service_with_bus()
    run = _running_run(store)

    with pytest.raises(WorkflowApprovalError, match="not awaiting approval"):
        service.approve_step(run.workflow_id, "gate", actor_user_id="s",
                             actor_roles=["supervisor"])


def test_rejecting_fails_the_run_with_the_reason_recorded() -> None:
    service, store, event_bus = _service_with_bus()
    run = _parked_run(store, step_id="gate")

    service.reject_step(run.workflow_id, "gate", actor_user_id="supervisor-1",
                        actor_roles=["supervisor"], reason="insufficient evidence")

    updated = store.get_run(run.workflow_id)
    assert updated.status is WorkflowRunStatus.FAILED
    assert updated.metadata["last_error"] == "insufficient evidence"
    assert not [e for e in event_bus.published_events
                if isinstance(e, WorkflowStepQueuedEvent)]


def test_a_second_approval_does_not_republish(caplog) -> None:
    """At-least-once clients retry. Two approvals must not run the step twice."""
    service, store, event_bus = _service_with_bus()
    run = _parked_run(store, step_id="gate")
    kwargs = dict(actor_user_id="supervisor-1", actor_roles=["supervisor"])

    service.approve_step(run.workflow_id, "gate", **kwargs)
    service.approve_step(run.workflow_id, "gate", **kwargs)

    queued = [e for e in event_bus.published_events if isinstance(e, WorkflowStepQueuedEvent)]
    assert len(queued) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/agent/test_service.py -k approve -v`
Expected: FAIL — `AttributeError: 'AgentService' object has no attribute 'approve_step'`

- [ ] **Step 3: Implement on the agent service**

Order matters, and each guard has a reason:

```python
    def approve_step(self, workflow_id, step_id, *, actor_user_id, actor_roles):
        run = self._run_store.get_run(workflow_id)
        if run.status is not WorkflowRunStatus.AWAITING_APPROVAL:
            raise WorkflowApprovalError(f"Run '{workflow_id}' is not awaiting approval.")
        if run.actor_user_id is not None and run.actor_user_id == actor_user_id:
            raise WorkflowApprovalError(
                "The actor who requested a run may not approve their own step."
            )
        if run.metadata.get(f"approved.{step_id}"):
            return run          # already approved; do not republish
        ...
```

Set status back to `QUEUED` when releasing the gate. Do **not** set `RUNNING`:
the executor claims the step itself, and pre-setting `RUNNING` would make the
run indistinguishable from one already in flight.

`WorkflowApprovalError` goes in `agent/exceptions.py` and must **not** subclass
`ValueError` — the workflows router already maps `ValueError` elsewhere, and a
conflict reported as a validation error tells an operator the wrong thing.

- [ ] **Step 4: Add the routes with a role gate**

`require_role("supervisor")` — the same role that approves definitions and
governance baselines. Map `WorkflowApprovalError` to **409** (the run is in the
wrong state), and an unknown run to **404**.

Request/response contracts go in `api/contracts.py`:
`WorkflowStepApprovalRequest(reason: str | None)` and
`WorkflowStepRejectionRequest(reason: str)` — a rejection reason is required,
because "rejected" with no reason is an audit record that explains nothing.

- [ ] **Step 5: Write the audit record**

`action="workflow.step.approved"` / `"workflow.step.rejected"`,
`resource_type="workflow_run"`, `resource_id=workflow_id`,
`actor_user_id` and `actor_roles` from the caller — **not** derived from the run
(the whole point is that the approver differs from the requester).

- [ ] **Step 6: Assert the projection, not just the record (spec §4.4)**

Add a router test that goes through `TestClient` and asserts the **response
body**: approving returns the run with `status == "queued"`, rejecting returns
`status == "failed"`. `AWAITING_APPROVAL` was correct in the store and wrong in
the API for the life of the feature because every test asserted the store.

- [ ] **Step 7: Regenerate contracts**

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && npm run build && npm run lint && npm run test:run
```

`npm run build` is not optional — see spec §4.5.

- [ ] **Step 8: Commit**

```bash
git add backend/agent backend/api backend/tests chili_app
git commit -m "feat(workflows): approve and reject a parked step, resuming the run"
```

---

### Task 6: Frontend approval control

**Files:**
- Modify: `chili_app/src/api/workflows.ts`, `chili_app/src/components/ingestion/RunTimeline.tsx`
- Test: `chili_app/src/components/ingestion/__tests__/RunTimeline.test.tsx`

**Interfaces:**
- Consumes: the routes from Task 5, via generated types in `src/api/contracts.ts`.

- [ ] **Step 1: Write the failing tests**

```tsx
it('offers approve and reject on a run parked at a gate', () => {
  render(<RunTimeline workflows={[parkedRun]} receipts={[]} />)

  expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
})

it('does not offer approval on a run that is merely running', () => {
  render(<RunTimeline workflows={[runningRun]} receipts={[]} />)

  expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
})

it('requires a reason before rejecting', async () => {
  render(<RunTimeline workflows={[parkedRun]} receipts={[]} />)
  await userEvent.click(screen.getByRole('button', { name: /reject/i }))

  expect(screen.getByRole('button', { name: /confirm/i })).toBeDisabled()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd chili_app && npm run test:run -- RunTimeline`
Expected: FAIL — no approve/reject controls

- [ ] **Step 3: Implement**

Add `useApproveWorkflowStep` / `useRejectWorkflowStep` mutations beside the
existing `useCancelWorkflow`, invalidating the same query keys so the timeline
refreshes. Import DTOs from `src/api/contracts.ts` — never hand-write wire
types, never `as any`.

- [ ] **Step 4: Run the full frontend gate set**

```bash
cd chili_app && npm run lint && npm run test:run && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add chili_app
git commit -m "feat(frontend): approve or reject a workflow run parked at a gate"
```

---

### Task 7: Live-stack verification

**Files:**
- Create: `backend/tests/e2e/test_approval_and_replay_flow.py`
- Modify: `docs/ledger/module-map.md`, `docs/project/planning/backlog.md`

In-process tests cannot discover unreachability (spec §4.2). Every defect this
plan closes was invisible to a green unit suite.

- [ ] **Step 1: Write the integration test**

Follow `tests/e2e/test_workflow_run_flow.py` — `pytestmark = pytest.mark.integration`,
skip unless the stack answers, talk HTTP only.

```python
def test_a_parked_run_resumes_after_approval(base_url: str) -> None:
    """The gap this plan exists for: parking was a dead end at both ends."""
    kb_id, run_id = _start_approval_gated_run(base_url)
    parked = _poll_until(base_url, run_id, statuses={"awaiting_approval"})
    assert parked["status"] == "awaiting_approval"

    response = requests.post(
        f"{base_url}/workflows/{run_id}/steps/gate/approve", json={}, timeout=30
    )
    assert response.status_code == 200, response.text

    resumed = _poll_until(base_url, run_id, statuses={"completed", "failed"})
    assert resumed["status"] == "completed", resumed


def test_rejecting_a_parked_run_fails_it(base_url: str) -> None: ...


def test_a_replayed_score_run_executes(base_url: str) -> None:
    """Live-confirmed broken 2026-08-07: replayed run stayed queued, scored=0."""
    kb_id, run_id = _completed_score_run(base_url)
    _force_batches_failed(run_id)
    replayed = requests.post(
        f"{base_url}/knowledgebases/{kb_id}/score-runs/{run_id}/replay",
        json={"requested_by": "e2e"}, timeout=30,
    ).json()["run"]["id"]

    final = _poll_score_run_until_terminal(base_url, kb_id, replayed)
    assert final["status"] == "completed", final
    assert final["scored_entities"] + final["failed_entities"] == final["total_entities"]


def test_a_stalled_connector_run_is_reconciled(base_url: str) -> None:
    """Ages a running sync run past the window and waits for the sweep."""
```

`_force_batches_failed` needs direct database access, which an HTTP-only test
does not have. Either drive it through `docker exec … psql` from the test (ugly
but honest), or add a test-only route guarded by `CHILI_ENV=local`. Prefer the
former: a test-only production route is a permanent liability for a temporary
convenience.

- [ ] **Step 2: Run it against the live stack**

```bash
make dev
cd backend && .venv/bin/pytest tests/e2e/test_approval_and_replay_flow.py -v -m integration
```

Docker commands run in the main session, not a subagent.

- [ ] **Step 3: Verify the worker side, not just the API**

For the approval case, confirm in the worker log that the step actually
dispatched after approval — an API that returns 200 and a run that reaches
`completed` could both be true while the step was skipped. Check the persisted
step status is `completed` with `attempts >= 1`.

- [ ] **Step 4: Update the docs that describe these as gaps**

`docs/ledger/module-map.md` currently says, under `workflow_definitions/`:
*"there is no approval endpoint, so a parked run is currently unparked only by
writing `approved.<step_id>` onto the run's metadata"* — replace with what
ships. Under `connectors/`: *"there is no reconciler"* — same. Add the score-run
replay fix to the `analytics/score_runs/` entry.

State plainly what is still open: the dashboard does not count
`awaiting_approval` (Plan 3), and four capabilities remain unbound (Plan 2).

- [ ] **Step 5: Run the full gates**

```bash
cd backend && .venv/bin/pytest --cov -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .
cd ../tools && ../backend/.venv/bin/pyright
cd ../chili_app && npm run lint && npm run test:run && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add backend/tests/e2e docs
git commit -m "test(workflows): live-stack verification of approval resume, score replay and connector reconciliation"
```

---

## Self-review notes

- **Spec coverage:** G1 (Tasks 5–7), G5 (Task 4), G4 (Tasks 1–3). D1 is
  implemented in Task 5 including the self-approval prohibition.
- **Sequencing:** Tasks 1–3 are independent of 4–6 and can run in parallel by
  separate agents. Task 7 requires all of them.
- **Migration:** Task 1 adds `0026`. If another branch adds a migration
  concurrently, rebase and renumber before merging — two `0026`s is an alembic
  branch, not a merge conflict, and CI's replay job will catch it.
- **Known trap:** `update_run` in both connector adapters always stamps
  `updated_at`, so a test cannot age a run through the public API. Task 1 Step 3
  addresses this deliberately rather than letting the reconciler go untested.
