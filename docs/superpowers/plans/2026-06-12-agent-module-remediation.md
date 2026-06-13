# Agent Module Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the reviewed agent-module bugs and harden workflow integration across API, worker, persistence, security, and observability.

**Architecture:** Keep `agent/` as the workflow owner, `api/` as the HTTP gateway, and `events/` as the transport boundary. Prefer protocol extensions and small helper modules over growing `coordinator.py` further, but do not restructure unrelated code.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Redis Streams, pytest, pyright strict.

---

### Task 1: Reject Missing KBs For Record File Uploads

**Issue:** `POST /records/{kb}/files` accepts a nonexistent KB and starts records/workflow side effects.

**Files:**
- Modify: `backend/api/routers/records.py`
- Test: `backend/tests/api/test_records_router.py`

- [ ] Add a test named `test_upload_file_rejects_missing_knowledge_base` that posts a valid CSV to `/records/missing-kb/files` and expects `404`.
- [ ] In `upload_record_file`, immediately after `existing_kb = repository.get(knowledge_base_id)`, add the same missing-KB 404 branch used by `push_records`:

```python
if existing_kb is None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Knowledge base '{knowledge_base_id}' was not found.",
    )
```

- [ ] Keep the existing pending-cleanup and busy checks after the existence check.
- [ ] Run `uv run --project backend pytest backend/tests/api/test_records_router.py::test_upload_file_rejects_missing_knowledge_base -q`.
- [ ] Run `uv run --project backend pytest backend/tests/api/test_records_router.py -q`.

### Task 2: Consume `documents.failed` Workflow Events

**Issue:** `IngestionService.ingest_task` publishes `documents.failed`, but the worker does not consume it, so workflows can remain active until stale reconciliation.

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_coordinator.py`

- [ ] Add `"documents.failed"` to `WORKER_EVENT_TYPES` next to the document pipeline event types.
- [ ] Add a focused test that `WORKER_EVENT_TYPES` contains `"documents.failed"`.
- [ ] Add a focused drain test with a seeded running workflow for `correlation_id="corr-doc-failed"` and a `DocumentsFailedEvent`; after one drain, assert the run is `FAILED` and the parse step is `FAILED`.
- [ ] Do not add a new handler branch unless needed; the existing dispatch default can return `0` after the tracker marks completion.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_coordinator.py -k "documents_failed or worker_event_types" -q`.

### Task 3: Make Correlation ID Claim Atomic

**Issue:** `RedisWorkflowRunStore.save_run` can create duplicate runs for the same `metadata["correlation_id"]`.

**Files:**
- Modify: `backend/agent/adapters/in_memory.py`
- Modify: `backend/agent/adapters/redis_store.py`
- Test: `backend/tests/agent/test_in_memory_adapter.py`
- Test: `backend/tests/agent/test_redis_workflow_run_store.py`

- [ ] Add tests for both stores: saving a second run with the same correlation id and a different workflow id raises `ValueError` and leaves the index pointing to the original run.
- [ ] In `InMemoryWorkflowRunStore.save_run`, enforce uniqueness of a string `correlation_id` the same way idempotency keys are enforced.
- [ ] In `RedisWorkflowRunStore.save_run`, use `SET ... NX` for the correlation key before persisting the run. If an existing value differs from the incoming `workflow_id`, raise `ValueError`.
- [ ] Ensure updating the same workflow id remains allowed.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_in_memory_adapter.py backend/tests/agent/test_redis_workflow_run_store.py -q`.

### Task 4: Make Workflow Started Notification Non-Critical

**Issue:** Failure to publish `agent.workflow.started` can fail API submission even though the primary pipeline event was already queued.

**Files:**
- Modify: `backend/agent/service.py`
- Test: `backend/tests/agent/test_service.py`

- [ ] Change `AgentService.start_workflow` so failure to publish `AgentWorkflowStartedEvent` does not mark the workflow `FAILED` and does not raise. Persist metadata key `workflow_started_publish_error` with a redacted/generic failure string, keep the run `RUNNING`, and return a normal response.
- [ ] Add `workflow_started_publish_error` to `SYSTEM_METADATA_KEYS` in `backend/agent/models.py` if idempotency comparisons need to ignore it.
- [ ] Update `test_agent_service_records_failed_run_when_publish_fails` to assert the run remains `RUNNING`, response succeeds, and metadata contains the non-critical publish error.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_service.py -q`.

### Task 5: Add Workflow Route Scope Enforcement Hooks

**Issue:** workflow routes are role-gated only and lack KB/tenant scope predicates.

**Files:**
- Modify: `backend/api/routers/workflows.py`
- Modify: `backend/api/middleware/rbac.py` if a reusable helper is needed
- Test: `backend/tests/api/test_workflows_router.py`

- [ ] Thread the authenticated `User` returned by `require_role` into list/read/cancel route bodies instead of using role dependencies only.
- [ ] Add a small private helper in `workflows.py`:

```python
def _can_access_workflow(user: User, knowledge_base_id: str) -> bool:
    allowed = getattr(user, "knowledge_base_ids", None)
    return allowed is None or knowledge_base_id in allowed or "admin" in user.roles
```

- [ ] If `User` has no KB-scope field today, keep behavior permissive but centralize the hook and add tests using a monkeypatched/dummy user object with `knowledge_base_ids=["kb-1"]`.
- [ ] For list, filter returned runs through `_can_access_workflow`.
- [ ] For get/cancel, return `404` for inaccessible runs to avoid ID enumeration.
- [ ] Run `uv run --project backend pytest backend/tests/api/test_workflows_router.py -q`.

### Task 6: Add Workflow Store Health Surface And Redis Timeouts

**Issue:** Redis workflow store has no bounded timeouts or health probe.

**Files:**
- Modify: `backend/agent/adapters/protocols.py`
- Modify: `backend/agent/adapters/redis_store.py`
- Modify: `backend/agent/adapters/in_memory.py`
- Modify: `backend/agent/adapters/runtime.py`
- Test: `backend/tests/agent/test_runtime.py`
- Test: `backend/tests/agent/test_redis_workflow_run_store.py`

- [ ] Add a `StoreHealth` Pydantic or dataclass model with `status: Literal["ok", "unhealthy"]`, `latency_ms: float | None`, and `error: str | None`.
- [ ] Add `check_health() -> StoreHealth` to `WorkflowRunStoreProtocol`.
- [ ] Implement in-memory as always ok.
- [ ] Implement Redis as `PING` with elapsed monotonic time; catch `RedisError` and return unhealthy.
- [ ] Extend `RedisWorkflowRunStore.__init__` with defaults: `socket_connect_timeout=2.0`, `socket_timeout=2.0`, `retry_on_timeout=True`, `health_timeout_seconds=2.0`, and pass the timeout options to `Redis.from_url`.
- [ ] Add env support for `CHILI_WORKFLOW_REDIS_SOCKET_TIMEOUT_SECONDS` and `CHILI_WORKFLOW_REDIS_CONNECT_TIMEOUT_SECONDS`.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_runtime.py backend/tests/agent/test_redis_workflow_run_store.py -q`.

### Task 7: Add Redis Workflow Listing Indexes And Pagination Metadata

**Issue:** Redis `list_runs` scans the entire created index and `/workflows` returns no pagination envelope.

**Files:**
- Modify: `backend/agent/adapters/redis_store.py`
- Modify: `backend/agent/adapters/in_memory.py`
- Modify: `backend/agent/adapters/protocols.py`
- Modify: `backend/agent/service.py`
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/_workflow_projection.py`
- Modify: `backend/api/routers/workflows.py`
- Test: `backend/tests/agent/test_redis_workflow_run_store.py`
- Test: `backend/tests/agent/test_in_memory_adapter.py`
- Test: `backend/tests/api/test_workflows_router.py`

- [ ] Introduce a generic `PageResult[T]` or workflow-specific `WorkflowRunPage` with `items`, `has_more`, and `next_offset`.
- [ ] Maintain Redis sorted indexes for all runs, per KB, per status, and per `(kb,status)`; delete stale index entries when status or KB changes.
- [ ] Use the narrowest index based on filters and fetch `limit + 1` IDs to compute `has_more`.
- [ ] Add `has_more: bool` and `next_offset: int | None` to `WorkflowRunListResponse`.
- [ ] Preserve existing `limit`/`offset` query params.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_redis_workflow_run_store.py backend/tests/agent/test_in_memory_adapter.py backend/tests/api/test_workflows_router.py -q`.

### Task 8: Validate Workflow Definitions

**Issue:** requested steps are free-form and event-to-step mapping is hardcoded.

**Files:**
- Create: `backend/agent/definitions.py`
- Modify: `backend/agent/workflow_tracking.py`
- Modify: `backend/agent/service.py`
- Test: `backend/tests/agent/test_definitions.py`
- Test: `backend/tests/agent/test_service.py`
- Test: `backend/tests/agent/test_workflow_tracking.py`

- [ ] Add `WorkflowStepDef`, `WorkflowDefinition`, and `WorkflowDefinitionRegistry` models.
- [ ] Register the current default sequence and event mapping from `workflow_tracking.py`.
- [ ] Replace `_STEP_BY_EVENT_TYPE` and `_DEFAULT_STEP_SEQUENCE` consumers with registry accessors while preserving public `default_steps_for_trigger`.
- [ ] In `AgentService.start_workflow`, reject unknown requested step names by raising `AgentConfigurationError`.
- [ ] Add tests for unknown step rejection and default plan parity.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_definitions.py backend/tests/agent/test_service.py backend/tests/agent/test_workflow_tracking.py -q`.

### Task 9: Make Graph Analytics Fan-Out Retryable

**Issue:** Flow B analytics fan-out from `GraphUpdatedEvent` is best-effort and can be silently partial.

**Files:**
- Modify: `backend/agent/coordinator.py`
- Test: `backend/tests/agent/test_coordinator.py`

- [ ] Remove the broad swallow around `handle_graph_updated_for_analytics` only when the failure happens before retryable follow-up events are published.
- [ ] If preserving Flow A isolation, publish an `AnalysisFailedEvent` with stage `analytics_fanout` on failures and mark workflow metadata with a non-terminal warning.
- [ ] Add a test where `handle_graph_updated_for_analytics` raises before publishing risk/alert events and assert either the event is retried/DLQed or an `AnalysisFailedEvent` is emitted; choose one behavior and document it.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_coordinator.py -k analytics -q`.

### Task 10: Add Stage-Level Retry Policy Hooks

**Issue:** one global retry policy is applied to every handler and every `Exception`.

**Files:**
- Create: `backend/agent/policy.py`
- Modify: `backend/agent/coordinator.py`
- Modify: `backend/agent/models.py`
- Test: `backend/tests/agent/test_coordinator.py`

- [ ] Add `StagePolicy` with `retry_policy`, `timeout_seconds`, and `fatal_exception_types`.
- [ ] Add `StagePolicyRegistry` keyed by event type with default fallback to current `RetryPolicy`.
- [ ] Update `run_handler_with_retry` to accept a stage policy and skip retry for fatal exception types.
- [ ] Use `asyncio.wait_for(asyncio.to_thread(handler), timeout=policy.timeout_seconds)` when timeout is set.
- [ ] Add tests for fatal exception no-retry and timeout retry.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_coordinator.py -k "policy or retry or timeout" -q`.

### Task 11: Count Queued Workflows As Active In API Projection

**Issue:** UI active workflow counters only count `RUNNING`, while busy checks treat `QUEUED` and `RUNNING` as active.

**Files:**
- Modify: `backend/api/_workflow_projection.py`
- Test: `backend/tests/api/test_workflow_projection.py`

- [ ] Update `count_running_workflows` to include `WorkflowRunStatus.QUEUED` and `WorkflowRunStatus.RUNNING`, or rename only if all callers are updated.
- [ ] Add a test with one queued, one running, and one completed run; expect count `2`.
- [ ] Run `uv run --project backend pytest backend/tests/api/test_workflow_projection.py -q`.

### Task 12: Add A Real Redis Contract Test Path

**Issue:** Redis workflow store tests use a hand fake and do not cover real Redis behavior.

**Files:**
- Modify: `backend/tests/agent/test_redis_workflow_run_store.py`
- Modify: `backend/pyproject.toml` only if a new marker is needed

- [ ] Keep existing fake tests for speed.
- [ ] Add integration tests marked `@pytest.mark.integration` that read `REDIS_URL`, create `RedisWorkflowRunStore(redis_url=REDIS_URL, key_prefix=f"test:{generate_id()}:" )`, save/list/update/delete a run, and assert indexes are cleared.
- [ ] Skip with a clear message when `REDIS_URL` is unset.
- [ ] Run `uv run --project backend pytest backend/tests/agent/test_redis_workflow_run_store.py -q`.
- [ ] If Redis is available, run `uv run --project backend pytest -m integration backend/tests/agent/test_redis_workflow_run_store.py -q`.

---

## Final Verification

- [ ] Run `uv run --project backend pytest backend/tests/agent backend/tests/api/test_workflows_router.py backend/tests/api/test_records_router.py backend/tests/api/test_workflow_projection.py -q`.
- [ ] Run `uv run --project backend pyright`.
- [ ] Run `git status --short` and report changed files.
