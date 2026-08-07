# Workflow Run Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an approved workflow definition actually run — dispatching each step through a fail-closed capability registry, honouring conditions, retries, failure modes and human approval gates, and auditing every tool call.

**Architecture:** Reuses the `execution/` dispatch seam. Adds `CapabilityRegistryService.execute()`, closes four fail-open branches in `authorize()`, adds a restricted condition evaluator (never `eval`), and executes one step per event so retry and cancellation inherit the substrate's semantics.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Redis Streams, pytest.

**Spec:** `docs/superpowers/specs/2026-08-06-execution-engines-design.md` §4.3

**Depends on:** `2026-08-06-score-all-executor.md` Tasks 1–6 (the `execution/` module must exist).

> **Security note.** Every fail-open branch listed in Task 1 is currently latent because nothing dispatches. Task 2 creates the dispatcher. **Task 1 must land before Task 2** — building the dispatcher first makes all four bypasses live.

## Global Constraints

- Python 3.12. Full type annotations; **no `Any`**. Bare `backend/.venv/bin/pyright` must report 0 errors. `capabilities/` and the `capabilities`/`workflow_definitions` routers are now inside `tool.pyright.include`.
- `backend/.venv/bin/ruff check --no-cache .` must pass.
- Tests run from `backend/`. **Never use a cwd-relative path in a test** — use `Path(__file__).resolve().parents[2]`.
- Coverage ≥ 85% per package.
- Executors **raise**; `run_handler_with_retry` owns retry vs dead-letter.
- **Never use `eval`, `exec`, or `compile` on a `condition` string.** It is user-authored content in a multi-tenant system.
- Any frontend-consumed Pydantic change requires OpenAPI export + `npm run codegen:api`.

## File Structure

| File | Responsibility |
|---|---|
| `backend/capabilities/service.py` | Fail-closed `authorize()`; new `execute()` |
| `backend/capabilities/executors.py` | `capability_id → callable` execution map |
| `backend/workflow_definitions/conditions.py` | Restricted condition grammar + evaluator |
| `backend/workflow_definitions/executor.py` | The step handler |
| `backend/agent/models.py` | `WorkflowStepState.attempts` (spec decision D1) |
| `backend/events/types.py` | `WorkflowStepQueuedEvent` |

---

### Task 1: Make `authorize()` fail closed

Four branches, not three — the empty-`required_roles` bypass exists in two functions.

**Files:**
- Modify: `backend/capabilities/service.py:78` (domain), `:89` (environment), `:190` (`_roles_can_access`), `:201` (`_role_can_access`)
- Test: `backend/tests/capabilities/test_registry.py`

**Interfaces:**
- Produces: `authorize(capability_id, *, actor_roles, domain_name, environment_tag)` — `domain_name` and `environment_tag` become **required** keyword arguments.

- [ ] **Step 1: Write the failing tests**

```python
def test_authorize_denies_when_domain_is_not_supplied() -> None:
    service = _service_with(_manifest(domains=["medicare_fraud"]))
    envelope = service.authorize(
        "analytics.peer_context",
        actor_roles=["analyst"],
        domain_name=None,
        environment_tag="local",
    )
    assert envelope.success is False
    assert envelope.error_code == "domain_not_supplied"


def test_authorize_denies_when_environment_is_not_supplied() -> None:
    service = _service_with(_manifest(environments=["local"]))
    envelope = service.authorize(
        "analytics.peer_context",
        actor_roles=["analyst"],
        domain_name="medicare_fraud",
        environment_tag=None,
    )
    assert envelope.success is False
    assert envelope.error_code == "environment_not_supplied"


def test_authorize_denies_a_capability_with_no_required_roles() -> None:
    """An empty required_roles used to mean 'everyone'. It now means 'nobody'."""
    service = _service_with(_manifest(required_roles=[]))
    envelope = service.authorize(
        "analytics.peer_context",
        actor_roles=["admin"],
        domain_name="medicare_fraud",
        environment_tag="local",
    )
    assert envelope.success is False
    assert envelope.error_code == "no_roles_permitted"


def test_role_can_access_denies_with_no_required_roles() -> None:
    """The second copy of the bypass — _role_can_access, used by the browse API."""
    assert _role_can_access(_manifest(required_roles=[]), "admin") is False


def test_authorize_denies_an_unregistered_capability() -> None:
    envelope = _service().authorize(
        "does.not.exist",
        actor_roles=["admin"],
        domain_name="medicare_fraud",
        environment_tag="local",
    )
    assert envelope.success is False
    assert envelope.error_code == "capability_not_registered"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/capabilities/test_registry.py -k "denies" -v`
Expected: FAIL — the first three return `success=True`; `_role_can_access` returns `True`

- [ ] **Step 3: Close the four branches**

```python
        if domain_name is None:
            return self._denied(capability_id, "domain_not_supplied",
                                "Capability authorization requires a domain.")
        if not _supports_domain(manifest, domain_name):
            ...
        if environment_tag is None:
            return self._denied(capability_id, "environment_not_supplied",
                                "Capability authorization requires an environment.")
```

And in both role helpers, invert the empty case:

```python
    required_roles = manifest.permission.required_roles
    if not required_roles:
        return False        # a capability granting no role is callable by nobody
```

Make `domain_name` and `environment_tag` required keyword args so a caller cannot omit them silently.

- [ ] **Step 4: Fix the two existing adapters**

`backend/workflow_definitions/rag_adapter.py:23-24` and `backend/connectors/status_adapter.py:23-24` default both dimensions to `None`. Make them required and thread the values through. Any capability manifest shipping `required_roles=[]` must be given real roles — check `backend/capabilities/registry.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/capabilities/ tests/workflow_definitions/ tests/connectors/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/capabilities/ backend/workflow_definitions/rag_adapter.py backend/connectors/status_adapter.py backend/tests/capabilities/test_registry.py
git commit -m "fix(capabilities): fail closed on omitted domain, omitted environment, and empty required_roles"
```

---

### Task 2: `CapabilityRegistryService.execute()`

**Files:**
- Create: `backend/capabilities/executors.py`
- Modify: `backend/capabilities/service.py`
- Test: `backend/tests/capabilities/test_execute.py`

**Interfaces:**
- Consumes: fail-closed `authorize()` from Task 1.
- Produces: `execute(capability_id, *, payload: Mapping[str, object], actor_roles, domain_name, environment_tag, knowledge_base_id, audit_service) -> CapabilityExecutionEnvelope`.

- [ ] **Step 1: Write the failing tests**

```python
def test_execute_denies_before_invoking_the_executor() -> None:
    invoked: list[str] = []
    service = _service_with_executor(lambda payload: invoked.append("ran"))

    envelope = service.execute(
        "analytics.peer_context",
        payload={},
        actor_roles=["viewer"],          # capability requires analyst
        domain_name="medicare_fraud",
        environment_tag="local",
        knowledge_base_id="kb-1",
        audit_service=_audit(),
    )

    assert envelope.success is False
    assert invoked == []                 # authorization runs BEFORE dispatch


def test_execute_writes_an_audit_event_when_requires_audit_is_set() -> None:
    audit = _audit()
    service = _service_with_executor(lambda payload: {"ok": True})

    service.execute(
        "analytics.peer_context", payload={}, actor_roles=["analyst"],
        domain_name="medicare_fraud", environment_tag="local",
        knowledge_base_id="kb-1", audit_service=audit,
    )

    events = audit.list_events(AuditEventQuery(knowledge_base_id="kb-1"))
    assert events.total_items == 1
    assert events.items[0].action == "capability.execute"


def test_execute_returns_a_failure_envelope_when_the_executor_raises() -> None:
    def _boom(payload: Mapping[str, object]) -> Mapping[str, object]:
        raise RuntimeError("upstream down")

    envelope = _service_with_executor(_boom).execute(...)
    assert envelope.success is False
    assert envelope.error_code == "capability_execution_failed"


def test_execute_denies_a_capability_with_no_registered_executor() -> None:
    envelope = _service_without_executor().execute(...)
    assert envelope.success is False
    assert envelope.error_code == "capability_not_executable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/capabilities/test_execute.py -v`
Expected: FAIL — `CapabilityRegistryService` has no attribute `execute`

- [ ] **Step 3: Implement `executors.py`**

```python
CapabilityExecutor = Callable[[Mapping[str, object]], Mapping[str, object]]

_EXECUTORS: dict[str, CapabilityExecutor] = {}


def register_executor(capability_id: str, executor: CapabilityExecutor) -> None:
    _EXECUTORS[capability_id] = executor


def get_executor(capability_id: str) -> CapabilityExecutor | None:
    return _EXECUTORS.get(capability_id)
```

- [ ] **Step 4: Implement `execute()`**

Order is the security property — authorize, then dispatch, then audit:

```python
    def execute(self, capability_id: str, *, payload, actor_roles,
                domain_name, environment_tag, knowledge_base_id,
                audit_service) -> CapabilityExecutionEnvelope:
        envelope = self.authorize(
            capability_id, actor_roles=actor_roles,
            domain_name=domain_name, environment_tag=environment_tag,
        )
        if not envelope.success:
            return envelope

        executor = get_executor(capability_id)
        if executor is None:
            return self.execution_failure(
                capability_id, "capability_not_executable",
                f"Capability '{capability_id}' has no registered executor.",
            )

        try:
            result = executor(payload)
        except Exception as exc:                       # noqa: BLE001
            outcome = self.execution_failure(
                capability_id, "capability_execution_failed", str(exc)
            )
        else:
            outcome = self.execution_success(capability_id, dict(result))

        if envelope.audit_required:
            audit_service.record(AuditEventCreate(
                tenant_id=PLATFORM_TENANT_ID,
                knowledge_base_id=knowledge_base_id,
                actor_user_id=_actor_id(actor_roles),
                action="capability.execute",
                resource_type="capability",
                resource_id=capability_id,
                outcome="success" if outcome.success else "failure",
                correlation_id=_correlation_id(),
            ))
        return outcome
```

This is where `CapabilityPermission.requires_audit` stops being a flag nothing reads.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/capabilities/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/capabilities/ backend/tests/capabilities/test_execute.py
git commit -m "feat(capabilities): add authorize-then-dispatch execute() with audit on side-effecting calls"
```

---

### Task 3: Restricted condition evaluator

**Files:**
- Create: `backend/workflow_definitions/conditions.py`
- Test: `backend/tests/workflow_definitions/test_conditions.py`

**Interfaces:**
- Produces: `evaluate_condition(condition: str, *, outputs: Mapping[str, Mapping[str, object]]) -> bool`, raising `ConditionSyntaxError` on anything outside the grammar.

Grammar — deliberately tiny: `<step_id>.<key> <op> <literal>` where `op ∈ {==, !=, >, >=, <, <=}` and `<literal>` is a quoted string, number, `true`, `false`, or `null`.

- [ ] **Step 1: Write the failing tests**

```python
def test_evaluates_a_simple_comparison() -> None:
    assert evaluate_condition(
        "enrich.risk_level == 'high'",
        outputs={"enrich": {"risk_level": "high"}},
    ) is True


def test_missing_step_output_is_false_not_an_error() -> None:
    assert evaluate_condition(
        "enrich.risk_level == 'high'", outputs={}
    ) is False


@pytest.mark.parametrize("hostile", [
    "__import__('os').system('rm -rf /')",
    "().__class__.__bases__[0].__subclasses__()",
    "open('/etc/passwd').read()",
    "enrich.__class__",
    "1 if exec('x=1') else 0",
])
def test_rejects_anything_outside_the_grammar(hostile: str) -> None:
    with pytest.raises(ConditionSyntaxError):
        evaluate_condition(hostile, outputs={})
```

The parametrised test is the point of this task. A workflow `condition` is user-authored; `eval` here is remote code execution.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/workflow_definitions/test_conditions.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the evaluator**

Tokenise with a regex over the grammar above and compare directly. Do **not** reach for `ast.literal_eval` on the whole expression, and never for `eval`. An unparseable condition raises `ConditionSyntaxError`; a resolvable reference to a missing output evaluates `False`.

- [ ] **Step 4: Validate conditions at authoring time**

Call `evaluate_condition`'s parser from `validate_workflow_definition_payload` so a malformed condition is rejected on create (422) rather than at run time.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/workflow_definitions/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/workflow_definitions/conditions.py backend/workflow_definitions/models.py backend/tests/workflow_definitions/test_conditions.py
git commit -m "feat(workflows): add a restricted condition grammar with no eval path"
```

---

### Task 4: `WorkflowStepState.attempts` and `WorkflowStepQueuedEvent`

Spec decision D1: `attempts` becomes a model field, not a `metadata` key.

**Files:**
- Modify: `backend/agent/models.py:91`, `backend/events/types.py`, `backend/events/codec.py`
- Test: `backend/tests/agent/test_models.py`, `backend/tests/events/test_codec.py`

**Interfaces:**
- Produces: `WorkflowStepState.attempts: int = 0`; `WorkflowStepQueuedEvent(event_type="workflow.step.queued", knowledge_base_id, workflow_id, definition_id, version, step_id)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_workflow_step_state_defaults_attempts_to_zero() -> None:
    assert WorkflowStepState(step_name="enrich").attempts == 0


def test_existing_serialized_step_without_attempts_still_loads() -> None:
    """Runs persisted before this field must deserialize."""
    state = WorkflowStepState.model_validate({"step_name": "enrich", "status": "pending"})
    assert state.attempts == 0


def test_event_codec_round_trips_workflow_step_queued_event() -> None:
    event = WorkflowStepQueuedEvent(
        correlation_id="c1", knowledge_base_id="kb-1", workflow_id="w1",
        definition_id="d1", version="v1", step_id="enrich",
    )
    decoded = decode_event(encode_event(event))
    assert isinstance(decoded, WorkflowStepQueuedEvent)
    assert decoded.step_id == "enrich"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/agent/test_models.py tests/events/test_codec.py -k "attempts or workflow_step" -v`
Expected: FAIL

- [ ] **Step 3: Add the field and the event**

`attempts: int = Field(default=0, ge=0)` on `WorkflowStepState`. No migration — `WorkflowRun` is persisted whole, so existing rows deserialize with the default.

Add the event class, `AnyEvent` member, `__all__`, codec entry, and `"workflow.step.queued"` in `WORKER_EVENT_TYPES`. Bump the event-catalog count from 34 to 35.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/agent/ tests/events/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agent/models.py backend/events/ backend/tests/ docs/ledger/event-catalog.md
git commit -m "feat(workflows): add step attempts and the workflow.step.queued event"
```

---

### Task 5: The workflow step executor

**Files:**
- Create: `backend/workflow_definitions/executor.py`
- Modify: `backend/execution/deps.py` (add `workflow_definition_repository`, `workflow_run_store`, `capability_registry`, `audit_service`)
- Test: `backend/tests/workflow_definitions/test_executor.py`

**Interfaces:**
- Consumes: `execute()` (Task 2), `evaluate_condition` (Task 3), `WorkflowStepQueuedEvent` (Task 4).
- Produces: `handle_workflow_step_queued(event: AnyEvent, deps: ExecutionDeps) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
def test_executor_runs_a_step_and_enqueues_the_next() -> None:
    deps, store = _deps_with_definition(steps=["enrich", "summarize"])
    handle_workflow_step_queued(_event(step_id="enrich"), deps)

    queued = [e for e in deps.event_bus.published_events
              if e.event_type == "workflow.step.queued"]
    assert [e.step_id for e in queued] == ["summarize"]


def test_a_false_condition_skips_the_step_without_executing_it() -> None:
    deps, store = _deps_with_definition(
        steps=["enrich"], condition="enrich.risk_level == 'high'"
    )
    handle_workflow_step_queued(_event(step_id="enrich"), deps)

    run = store.get_run(_WORKFLOW_ID)
    assert _step(run, "enrich").status == WorkflowStepStatus.SKIPPED


def test_an_approval_step_parks_the_run_and_does_not_dispatch() -> None:
    deps, store = _deps_with_definition(steps=["notify"], requires_approval=True)
    handle_workflow_step_queued(_event(step_id="notify"), deps)

    run = store.get_run(_WORKFLOW_ID)
    assert run.status == WorkflowRunStatus.AWAITING_APPROVAL
    assert deps.capability_registry.execute_call_count == 0


def test_fail_workflow_mode_terminates_the_run() -> None:
    deps, store = _deps_with_failing_step(on_failure=WorkflowFailureMode.FAIL_WORKFLOW)
    handle_workflow_step_queued(_event(step_id="enrich"), deps)

    run = store.get_run(_WORKFLOW_ID)
    assert run.status == WorkflowRunStatus.FAILED
    assert not [e for e in deps.event_bus.published_events
                if e.event_type == "workflow.step.queued"]


def test_continue_mode_proceeds_to_the_next_step() -> None:
    deps, store = _deps_with_failing_step(
        on_failure=WorkflowFailureMode.CONTINUE, steps=["enrich", "summarize"]
    )
    handle_workflow_step_queued(_event(step_id="enrich"), deps)

    queued = [e for e in deps.event_bus.published_events
              if e.event_type == "workflow.step.queued"]
    assert [e.step_id for e in queued] == ["summarize"]


def test_step_retries_up_to_max_attempts_then_fails() -> None:
    deps, store = _deps_with_failing_step(max_attempts=2, steps=["enrich"])
    handle_workflow_step_queued(_event(step_id="enrich"), deps)
    handle_workflow_step_queued(_event(step_id="enrich"), deps)

    run = store.get_run(_WORKFLOW_ID)
    assert _step(run, "enrich").attempts == 2
    assert run.status == WorkflowRunStatus.FAILED


def test_executor_stops_when_the_run_is_cancelled() -> None:
    deps, store = _deps_with_definition(steps=["enrich"])
    store.update_run(_WORKFLOW_ID, status=WorkflowRunStatus.CANCELLED)

    assert handle_workflow_step_queued(_event(step_id="enrich"), deps) == 0
    assert deps.capability_registry.execute_call_count == 0


def test_executor_is_idempotent_under_duplicate_delivery() -> None:
    """Spec 6.4 — a redelivered step event must not execute the capability twice.

    Without a guard this is worse than a miscount: a side-effecting capability
    (case note draft, connector sync) would run twice for one authored step.
    """
    deps, store = _deps_with_definition(steps=["enrich", "summarize"])
    event = _event(step_id="enrich")

    handle_workflow_step_queued(event, deps)
    handle_workflow_step_queued(event, deps)      # redelivered

    assert deps.capability_registry.execute_call_count == 1
    queued = [e for e in deps.event_bus.published_events
              if e.event_type == "workflow.step.queued"]
    assert [e.step_id for e in queued] == ["summarize"]   # enqueued once
```

A step already in a terminal status (`COMPLETED`, `SKIPPED`, `FAILED`) must return `0` before dispatch. That check is the idempotency guard — the step's own status is the claim.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/workflow_definitions/test_executor.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the executor**

Order: load run → cancelled check → resolve step → condition → approval gate → dispatch → apply `on_failure` → enqueue next.

```python
    if run.status in _TERMINAL_RUN_STATUSES:
        return 0
    if step.requires_human_approval and not _has_approval(run, step.step_id):
        run_store.update_run(run.workflow_id,
                             status=WorkflowRunStatus.AWAITING_APPROVAL)
        return 0                                   # server-side gate, not UI-only
    if step.condition is not None and not evaluate_condition(
        step.condition, outputs=_outputs_so_far(run)
    ):
        _mark(run, step, WorkflowStepStatus.SKIPPED)
        _enqueue_next(...)
        return 1

    envelope = deps.capability_registry.execute(
        step.capability_ref,
        payload=_payload_for(step, run),
        actor_roles=_run_actor_roles(run),
        domain_name=deps.domain_config.domain.name,
        environment_tag=_environment_tag(),
        knowledge_base_id=run.knowledge_base_id,
        audit_service=deps.audit_service,
    )
```

Register with `register_handler("workflow.step.queued", handle_workflow_step_queued)` and import from `backend/execution/__init__.py`.

- [ ] **Step 4: Publish the first step from `run_definition`**

`WorkflowDefinitionService.run_definition` currently saves a `QUEUED` run and stops. Publish `WorkflowStepQueuedEvent` for the first step after `save_run` so the chain starts.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/workflow_definitions/ -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/workflow_definitions/executor.py backend/workflow_definitions/service.py backend/execution/deps.py backend/tests/workflow_definitions/test_executor.py
git commit -m "feat(workflows): execute steps with conditions, retries, failure modes and approval gating"
```

---

### Task 6: Exclude parked runs from stale reconciliation

Spec §6.8 — an approval left overnight must not be reaped as a stalled run.

**Files:**
- Modify: `backend/agent/workflow_tracking.py:198`
- Test: `backend/tests/agent/test_workflow_tracking.py`

- [ ] **Step 1: Write the failing test**

```python
def test_reconcile_does_not_fail_a_run_awaiting_approval() -> None:
    store = InMemoryWorkflowRunStore()
    run = store.save_run(_run(status=WorkflowRunStatus.AWAITING_APPROVAL,
                              updated_at=_hours_ago(48)))
    tracker = WorkflowEventTracker(store)

    assert tracker.reconcile_stale_runs(max_age_seconds=3600) == 0
    assert store.get_run(run.workflow_id).status == WorkflowRunStatus.AWAITING_APPROVAL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/agent/test_workflow_tracking.py -k awaiting_approval -v`
Expected: FAIL — the run is reaped and marked failed

- [ ] **Step 3: Exclude the status**

`reconcile_stale_runs` iterates `(QUEUED, RUNNING)`. `AWAITING_APPROVAL` must never be added to that tuple; add an explicit guard and a comment saying why, so a later edit does not reintroduce it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/agent/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agent/workflow_tracking.py backend/tests/agent/test_workflow_tracking.py
git commit -m "fix(workflows): never reap a run parked awaiting approval"
```

---

### Task 7: Live-stack verification and docs

**Files:**
- Test: `backend/tests/e2e/test_workflow_run_flow.py`
- Modify: `docs/ledger/module-map.md`, `docs/architecture.md`, `docs/project/planning/backlog.md`

- [ ] **Step 1: Write the integration test**

```python
pytestmark = pytest.mark.integration


def test_approved_workflow_runs_to_completion() -> None:
    definition = _create_and_approve_definition(steps=["peer_context", "case_note"])
    workflow_id = _run(definition)

    run = _poll_until_terminal(workflow_id, timeout_seconds=120)

    assert run["status"] == "completed"
    assert [s["status"] for s in run["steps"]] == ["completed", "completed"]


def test_unauthorized_capability_denies_and_fails_the_run() -> None:
    """The release gate: a workflow must not invoke what it may not."""
    definition = _create_and_approve_definition(steps=["peer_context"], actor_roles=["viewer"])
    run = _poll_until_terminal(_run(definition), timeout_seconds=60)

    assert run["status"] == "failed"
    assert _audit_events(action="capability.execute")[0]["outcome"] == "failure"
```

- [ ] **Step 2: Run with the stack up**

```bash
make dev
cd backend && .venv/bin/pytest tests/e2e/test_workflow_run_flow.py -v -m integration
```

Docker commands run in the main session, not a subagent.

- [ ] **Step 3: Update the docs that say this does not work**

`docs/ledger/module-map.md` — the `workflow_definitions/` entry reads "No executor — no event is published and no worker consumes it, so steps never run", and `capabilities/` reads "there is no dispatcher". Replace both. `docs/architecture.md` should record that capability execution is authorize-then-dispatch and audited.

- [ ] **Step 4: Run the full gates**

```bash
cd backend && .venv/bin/pytest --cov -q && .venv/bin/pyright && .venv/bin/ruff check --no-cache .
cd ../ && ./backend/.venv/bin/python scripts/backlog_consistency.py --check
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/e2e/test_workflow_run_flow.py docs/ledger/module-map.md docs/architecture.md docs/project/planning/backlog.md
git commit -m "test(workflows): live-stack run verification; close the SAFE-CMS-014/015 executor gap"
```
