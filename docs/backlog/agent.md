# agent backlog

> **Scope:** Workflow coordinator, run lifecycle, worker dispatch, DLQ operations, run persistence.
> **Story format and rules:** see [design spec §5](../superpowers/specs/2026-05-24-complete-backlog-design.md#5-story-format).

---

## Story agent.01: Add async agent service boundary

**ID:** agent.01
**Status:** planned
**Prerequisites:** []
**Unblocks:** [_multitenancy.12, vectorstore.04]
**Estimated size:** M

**As a** platform engineer,
**I need** the `AgentServiceProtocol` and `AgentService` to expose `async` methods that perform run-store I/O and event-bus publish off the event loop,
**so that** FastAPI handlers in `backend/api/routers/workflows.py` no longer block the loop on Redis round-trips and the worker no longer needs sync shims to call agent service code.

### Current State
- `AgentServiceProtocol` declares only synchronous methods (`backend/agent/protocols.py:12-31`) with a `TODO(production): Add async variants` note.
- `AgentService.list_workflows` / `cancel_workflow` are sync and perform Redis I/O inline (`backend/agent/service.py:114-138`).
- `list_workflows` is awaited from an `async def` FastAPI route (`backend/api/routers/workflows.py:24-39`), so Redis calls run on the event loop.
- `start_workflow` publishes to the event bus synchronously (`backend/agent/service.py:69-83`) — another blocking call on the loop when reached from async routes.

### Acceptance Criteria
- [ ] `AgentServiceProtocol` exposes `async def start_workflow / get_workflow_status / list_workflows / cancel_workflow`.
- [ ] `AgentService` implements the async surface; sync I/O is wrapped via `asyncio.to_thread` or replaced with async clients (no blocking calls on the loop).
- [ ] `backend/api/routers/workflows.py` awaits the agent service without sync bridges.
- [ ] Worker callers (e.g. `WorkflowEventTracker`) keep a sync surface or are migrated; either way the test suite passes.
- [ ] `TODO(production)` async-variant comment in `protocols.py` is removed.

### Verification
- `pytest backend/tests/agent/ backend/tests/api/test_workflows.py` green, coverage ≥ 85% on `agent/`.
- `pyright --strict` clean on `agent/`, `api/routers/workflows.py`.
- A unit test asserts `inspect.iscoroutinefunction(AgentService.list_workflows)` and that calling it from a tight asyncio loop does not block measurable wall time when the store sleeps.

### Code touch points
- `backend/agent/protocols.py` (modify)
- `backend/agent/service.py` (modify)
- `backend/api/routers/workflows.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/tests/agent/test_service.py` (modify)
- `backend/tests/api/test_workflows.py` (modify)

---

## Story agent.02: Enforce hard cancellation before expensive worker stages

**ID:** agent.02
**Status:** planned
**Prerequisites:** [agent.04]
**Unblocks:** []
**Estimated size:** M

**As an** operator,
**I need** the worker coordinator to check workflow status and abort before each expensive handler stage,
**so that** cancellations issued via the API stop GNN/embedding/graph work that would otherwise burn minutes after the cancel.

### Current State
- `AgentService.cancel_workflow` only flips the status in the store (`backend/agent/service.py:129-138`) — no signal reaches the worker.
- `WorkflowEventTracker.begin_event` returns `False` when the run is terminal, but only after the event has been dispatched into the handler graph (`backend/agent/workflow_tracking.py:80-108`).
- `run_handler_with_retry` and `drain_ingestion_events` do not re-read run status before each handler (`backend/agent/coordinator.py:2345-2530`); long-running stages (GNN, embeddings) cannot be interrupted.

### Acceptance Criteria
- [ ] Every expensive handler (GNN, embeddings, monitoring, graph build) re-reads the workflow status from the run store before starting work and short-circuits when the run is `CANCELLED`/`FAILED`.
- [ ] Cancelled runs do not produce downstream events (e.g. `embeddings.complete`, `vectors.indexed`).
- [ ] A skip emits a structured log line with `workflow_id`, `correlation_id`, `stage` so cancellations are observable.
- [ ] Integration test demonstrates: enqueue → cancel → no further `*.complete` events for the cancelled workflow.

### Verification
- `pytest backend/tests/agent/test_coordinator.py -k cancel` green.
- Manual: `make dev`, submit a workflow, hit cancel; confirm worker logs `stage skipped: cancelled` and no further pipeline events for that `correlation_id`.
- Coverage ≥ 85% on `agent/`.

### Code touch points
- `backend/agent/coordinator.py` (modify)
- `backend/agent/workflow_tracking.py` (modify)
- `backend/tests/agent/test_coordinator.py` (modify)

---

## Story agent.03: Add indexed workflow lookup by correlation ID

**ID:** agent.03
**Status:** done
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** S
**Done:** implemented indexed correlation lookup in the workflow store protocol plus in-memory and Redis adapters; tracker and service code now use the indexed path.

**As a** worker,
**I need** O(1) lookup of a workflow run by its correlation ID,
**so that** tracker resolution scales beyond the current `list_runs(limit=1000)` linear scan and does not silently miss runs once the table grows past 1000 entries.

### Current State
- `WorkflowRunStoreProtocol.find_by_correlation_id(correlation_id)` is implemented and documented as an indexed lookup (`backend/agent/adapters/protocols.py`).
- `InMemoryWorkflowRunStore` and `RedisWorkflowRunStore` maintain the correlation-id index through save/update/delete (`backend/agent/adapters/in_memory.py`, `backend/agent/adapters/redis_store.py`).
- `WorkflowEventTracker._find_by_correlation_id` delegates to the store lookup, and `AgentService.start_workflow` uses the same lookup to adopt fallback runs when the worker won the race (`backend/agent/workflow_tracking.py`, `backend/agent/service.py`).

### Acceptance Criteria
- [x] `WorkflowRunStoreProtocol.find_by_correlation_id(correlation_id: str) -> WorkflowRun | None` added.
- [x] In-memory and Redis adapters maintain a `correlation_id -> workflow_id` index updated on `save_run` / `update_run` / `delete_run`.
- [x] `WorkflowEventTracker._find_by_correlation_id` uses the indexed lookup; the `limit=1000` scan is removed.
- [x] Coverage added for index lookup and index maintenance through update/delete cycles.

### Verification
- Covered by `backend/tests/agent/test_workflow_tracking.py`, `backend/tests/agent/test_in_memory_adapter.py`, `backend/tests/agent/test_redis_workflow_run_store.py`, and `backend/tests/agent/test_service.py`.

### Code touch points
- `backend/agent/adapters/protocols.py` (modify)
- `backend/agent/adapters/in_memory.py` (modify)
- `backend/agent/adapters/redis_store.py` (modify)
- `backend/agent/workflow_tracking.py` (modify)
- `backend/tests/agent/test_workflow_tracking.py` (modify)
- `backend/tests/agent/test_redis_store.py` (modify)

---

## Story agent.04: Make workflow store updates race-safe with conditional writes

**ID:** agent.04
**Status:** planned
**Prerequisites:** []
**Unblocks:** [agent.02, storage.05]
**Estimated size:** M

**As a** platform engineer,
**I need** `update_run` to use optimistic concurrency control (version or CAS) so concurrent worker + API writers cannot clobber each other's status transitions,
**so that** a user-issued `CANCELLED` cannot be silently overwritten by a stale worker `RUNNING` update.

### Current State
- `WorkflowRun` still has no `version` / `etag` field (`backend/agent/models.py`).
- `WorkflowRunStoreProtocol.update_run_if_current(...)` now provides status-conditional writes, and both in-memory and Redis adapters implement it.
- `WorkflowEventTracker` uses `update_run_if_current(expected_statuses={QUEUED, RUNNING})` for begin/complete/fail/stale-reconcile writes, so user cancellation is not clobbered by tracker writes.
- The remaining gap is stronger versioned optimistic concurrency for arbitrary concurrent writers, including `AgentService.cancel_workflow` and `update_run`.

### Acceptance Criteria
- [ ] `WorkflowRun` gains a monotonic `version: int` field (`Field(default=1)`).
- [ ] `WorkflowRunStoreProtocol.update_run` accepts an `expected_version: int | None` parameter; mismatch raises `WorkflowVersionConflictError`.
- [ ] Redis adapter uses `WATCH` / Lua to enforce the version check atomically.
- [ ] In-memory adapter enforces the same semantics under threaded contention (existing lock + version check).
- [ ] Tracker and `AgentService.cancel_workflow` retry on conflict (bounded) and surface a typed error if the run reached a terminal state mid-update.
- [ ] New tests: concurrent `cancel` + worker `update_run` does not clobber `CANCELLED`.

### Verification
- `pytest backend/tests/agent/test_redis_store.py -k version` green.
- Coverage ≥ 85% on `agent/`.
- `pyright --strict` clean.

### Code touch points
- `backend/agent/models.py` (modify)
- `backend/agent/adapters/protocols.py` (modify)
- `backend/agent/adapters/in_memory.py` (modify)
- `backend/agent/adapters/redis_store.py` (modify)
- `backend/agent/exceptions.py` (modify)
- `backend/agent/service.py` (modify)
- `backend/agent/workflow_tracking.py` (modify)
- `backend/tests/agent/test_redis_store.py` (modify)

---

## Story agent.05: Add workflow retention, archival, and idempotency TTL

**ID:** agent.05
**Status:** planned
**Prerequisites:** [config.04]
**Unblocks:** [agent.20]
**Estimated size:** M

**As an** operator,
**I need** workflow runs, idempotency keys, and created-at index entries to age out via TTL or scheduled cleanup,
**so that** Redis storage does not grow unbounded and idempotency keys do not block resubmission forever.

### Current State
- `RedisWorkflowRunStore.save_run` writes `SET`/`ZADD` without `EX` or expiry (`backend/agent/adapters/redis_store.py:39-72`).
- `WorkflowRunStoreProtocol` exposes no `purge_expired` / TTL surface (`backend/agent/adapters/protocols.py:11-49`).
- Idempotency keys are written via `SET` with no TTL (`backend/agent/adapters/redis_store.py:48`, `69-71`).
- No retention config block exists in `DomainConfig`.

### Acceptance Criteria
- [ ] `DomainConfig` (or new `AgentConfig`) exposes `run_retention_seconds`, `idempotency_ttl_seconds`, `cleanup_interval_seconds`.
- [ ] `WorkflowRunStoreProtocol.purge_expired(before: datetime) -> int` added; Redis + in-memory adapters implement it.
- [ ] Idempotency keys honour `idempotency_ttl_seconds` via Redis `EX`.
- [ ] Worker runs the purge task on the configured interval (or via a separate `chili-housekeeper` entry point) and emits a metric for purged rows.
- [ ] Tests cover: TTL respected on idempotency keys; `purge_expired` removes runs + cleans created-at index + correlation index.

### Verification
- `pytest backend/tests/agent/` green.
- Manual: set `run_retention_seconds=1`, submit a workflow, wait, observe purge log line.

### Code touch points
- `backend/agent/adapters/protocols.py` (modify)
- `backend/agent/adapters/in_memory.py` (modify)
- `backend/agent/adapters/redis_store.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/agent/test_redis_store.py` (modify)

---

## Story agent.06: Add audit-grade workflow lifecycle history

**ID:** agent.06
**Status:** planned
**Prerequisites:** [agent.18, database.07]
**Unblocks:** []
**Estimated size:** L

**As a** compliance reviewer,
**I need** every workflow lifecycle transition (submit, begin, complete, fail, cancel, retry, DLQ) appended to an immutable history,
**so that** audit logs reconstruct who/what/when for any workflow, satisfying the §14.2 audit-log capability.

### Current State
- `WorkflowRun` is a mutable current-state projection (`backend/agent/models.py:79-99`).
- `WorkflowEventTracker` overwrites `status`/`steps` in place via `update_run` (`backend/agent/workflow_tracking.py:99-165`); no append-only ledger.
- DLQ publishes log a line but never write to a history table (`backend/agent/coordinator.py:2402-2412`).
- No `workflow_history` / `workflow_events` table exists under `backend/database/`.

### Acceptance Criteria
- [ ] New `WorkflowHistoryEvent` model captures `workflow_id`, `event_type`, `from_status`, `to_status`, `step_name`, `actor`, `correlation_id`, `payload`, `created_at`.
- [ ] `WorkflowHistoryStoreProtocol` defined under `backend/agent/adapters/protocols.py` with Postgres + in-memory implementations.
- [ ] Alembic migration creates `workflow_history` with `(workflow_id, created_at)` index.
- [ ] `AgentService.start_workflow`, `cancel_workflow`, and all `WorkflowEventTracker` transitions append history rows (transactionally with the run-store update where the backend supports it).
- [ ] DLQ publish in `run_handler_with_retry` appends a `dlq_routed` history row with `retry_count`.
- [ ] History reads exposed via a typed query method, paginated.

### Verification
- `pytest backend/tests/agent/ backend/tests/database/` green; coverage ≥ 85% on `agent/`.
- Manual: submit → cancel a workflow; query `workflow_history` and observe `submitted`, `running`, `cancelled` rows in order.

### Code touch points
- `backend/agent/models.py` (modify)
- `backend/agent/adapters/protocols.py` (modify)
- `backend/agent/adapters/postgres_history.py` (new)
- `backend/agent/adapters/in_memory.py` (modify)
- `backend/agent/service.py` (modify)
- `backend/agent/workflow_tracking.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/database/migrations/versions/<new>_workflow_history.py` (new)
- `backend/tests/agent/test_history.py` (new)

---

## Story agent.07: Add worker leases, heartbeats, and stale-run reconciliation

**ID:** agent.07
**Status:** planned
**Prerequisites:** [events.06]
**Unblocks:** [agent.20, ingestion.23]
**Estimated size:** L

**As a** platform engineer,
**I need** workers to claim runs with a lease, heartbeat the lease, and a reconciler to recover runs orphaned by worker crashes,
**so that** a SIGKILLed worker does not leave runs stuck in `queued`/`running` forever.

### Current State
- `HealthState` tracks only `last_event_processed_at` in process memory (`backend/agent/health.py:22-57`).
- `WorkerDependencies` has no worker identity field (`backend/agent/coordinator.py:222-251`).
- No lease store, no heartbeat write, no reconciler exists in `backend/agent/`.
- Crashed workers leave Redis Streams pending entries indefinitely (visible via XPENDING but never reclaimed by chiliAI).

### Acceptance Criteria
- [ ] Each worker generates a stable `worker_id` (env or hostname+PID) and registers it in the run store on startup.
- [ ] `WorkflowRun` records `claimed_by: str | None` and `lease_expires_at: datetime | None`; the worker sets these when it begins handling a workflow's events.
- [ ] A heartbeat loop refreshes `lease_expires_at` every N seconds (configurable).
- [ ] A `WorkflowReconciler` task scans for runs whose lease has expired and either re-queues them or marks them `FAILED` with reason `worker_lost`.
- [ ] Stale Redis Streams pending entries are reclaimed via `XAUTOCLAIM` through the event-bus contract (depends on `events.06`).
- [ ] Tests: simulate crash by dropping the lease; reconciler recovers within one interval.

### Verification
- `pytest backend/tests/agent/test_reconciler.py` green.
- Manual: `make dev`, submit a workflow, `docker compose kill chili-worker`, restart; reconciler logs recovery within 60s.

### Code touch points
- `backend/agent/coordinator.py` (modify)
- `backend/agent/health.py` (modify)
- `backend/agent/models.py` (modify)
- `backend/agent/reconciler.py` (new)
- `backend/agent/adapters/protocols.py` (modify)
- `backend/agent/adapters/redis_store.py` (modify)
- `backend/agent/adapters/in_memory.py` (modify)
- `backend/tests/agent/test_reconciler.py` (new)

---

## Story agent.08: Build DLQ inspection, replay, and resolution workflows

**ID:** agent.08
**Status:** planned
**Prerequisites:** [events.07]
**Unblocks:** [agent.19, agent.20]
**Estimated size:** L

**As an** operator,
**I need** a typed service plus API to list, inspect, replay, ignore, and annotate DLQ entries — linked to their owning workflow runs,
**so that** failed events do not silently rot in the dead-letter stream.

### Current State
- `run_handler_with_retry` calls `event_bus.publish_to_dlq` and returns (`backend/agent/coordinator.py:2402-2413`); nothing else surfaces the DLQ contents.
- No agent-owned service exposes list/get/replay/resolve/ignore.
- `WorkflowRun` does not link to DLQ entries (`backend/agent/models.py:79-99`).

### Acceptance Criteria
- [ ] `DlqService` (under `backend/agent/dlq_service.py`) exposes `list_entries`, `get_entry`, `replay`, `resolve`, `ignore` — all async, all paginated.
- [ ] Each DLQ entry links to the originating `workflow_id` via `correlation_id` lookup.
- [ ] `DlqEntry` model captures `event`, `error`, `traceback`, `retry_count`, `dlq_status` (`pending`, `replayed`, `resolved`, `ignored`), `resolved_by`, `resolved_at`, `note`.
- [ ] Resolution writes a history row via `agent.06` (cross-edge: if `agent.06` lands later, store now and backfill).
- [ ] Replay re-publishes the original event with a `replay_of: <original_id>` metadata tag and increments a `replays_total` metric.
- [ ] Tests cover: replay success, replay failure, ignore, resolve.

### Verification
- `pytest backend/tests/agent/test_dlq_service.py` green.
- Coverage ≥ 85% on `agent/`.

### Code touch points
- `backend/agent/dlq_service.py` (new)
- `backend/agent/protocols.py` (modify)
- `backend/agent/models.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/tests/agent/test_dlq_service.py` (new)

---

## Story agent.09: Split worker liveness from readiness with dependency probes

**ID:** agent.09
**Status:** planned
**Prerequisites:** [graph.05, vectorstore.04, embeddings.05, storage.04, database.04, events.05]
**Unblocks:** [embeddings.10]
**Estimated size:** M

**As a** Kubernetes operator,
**I need** distinct `/live` and `/ready` endpoints on the worker that probe each dependency (`event bus`, `run store`, `graph`, `vector`, `embeddings`, `storage`, `DB`),
**so that** the orchestrator can route traffic correctly and restart only on liveness failures.

### Current State
- `/health` returns process-only status based on `last_event_processed_at` (`backend/agent/health.py:124-143`).
- No `/ready` endpoint exists; no dependency probes.
- `start_health_server_safely` mounts only the existing single endpoint (`backend/agent/coordinator.py:2559-2568`).

### Acceptance Criteria
- [ ] `/live` returns 200 whenever the worker process is responsive (and not in shutdown).
- [ ] `/ready` returns 200 only when all dependencies report healthy via their `check_health()` protocol methods (cross-edges).
- [ ] `/ready` returns 503 with a JSON body identifying the failing dependency.
- [ ] Probe timeouts are bounded (per-dependency, configurable; default 2s).
- [ ] Existing `/health` keeps current behavior for backwards compatibility; new endpoints documented in `backend/README.md`.
- [ ] Tests: unhealthy graph → `/ready` 503 names `graph`; healthy state → `/ready` 200.

### Verification
- `pytest backend/tests/agent/test_health.py` green.
- Manual: `make dev`, stop Neo4j, observe `/ready` flips to 503 within 5s.

### Code touch points
- `backend/agent/health.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/tests/agent/test_health.py` (modify)
- `backend/README.md` (modify)

---

## Story agent.10: Introduce typed AgentConfig / WorkerConfig with production guardrails

**ID:** agent.10
**Status:** planned
**Prerequisites:** [config.04]
**Unblocks:** [records.07, records.12]
**Estimated size:** M

**As a** platform engineer,
**I need** a typed `AgentConfig`/`WorkerConfig` section in `DomainConfig` covering run-store backend, retention, leases, concurrency, DLQ replay, and worker identity, with guardrails that reject in-memory stores in production,
**so that** misconfiguration cannot silently drop runs and configuration lives in one place instead of scattered env vars.

### Current State
- Run-store backend is selected via `CHILI_WORKFLOW_RUN_STORE_BACKEND` env var (`backend/agent/adapters/runtime.py:15-32`), outside `DomainConfig`.
- `build_worker_dependencies` reads env vars and `config.capabilities.gnn` ad hoc (`backend/agent/coordinator.py:609-725`).
- No production guardrail prevents `in_memory` store selection in a prod deployment.
- Retention, leases, concurrency, DLQ replay, and worker identity have no typed config block.

### Acceptance Criteria
- [ ] `DomainConfig.agent: AgentConfig` defined with sub-sections: `run_store` (backend literal + retention TTLs), `worker` (identity, concurrency caps, lease seconds), `dlq` (replay limits, ignore window).
- [ ] `runtime.py` reads from `AgentConfig` (env-var fallback retained, but config wins).
- [ ] When `config.environment == "production"`, in-memory adapters raise `AgentConfigurationError` at startup.
- [ ] `backend/config/defaults/*.yaml` includes a sane default `agent:` block.
- [ ] Tests: prod + in-memory fails fast; dev + in-memory succeeds; typo in backend literal raises a typed error.

### Verification
- `pytest backend/tests/agent/test_runtime.py backend/tests/config/` green.
- Coverage ≥ 85% on `agent/`, `config/`.

### Code touch points
- `backend/agent/adapters/runtime.py` (modify)
- `backend/agent/coordinator.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/config/defaults/medicare_fraud.yaml` (modify)
- `backend/tests/agent/test_runtime.py` (modify)

---

## Story agent.11: Add store-level indexes and API pagination for workflow listing

**ID:** agent.11
**Status:** planned
**Prerequisites:** []
**Unblocks:** [embeddings.07]
**Estimated size:** M

**As an** API consumer,
**I need** `list_workflows` to use a server-side `(kb, status, created_at)` index and the `/workflows` endpoint to return cursor/offset pagination with `has_more`,
**so that** the UI can page through tens of thousands of runs without scanning the whole sorted set on every request.

### Current State
- `RedisWorkflowRunStore.list_runs` reads the full `CREATED_INDEX` sorted set and filters by `knowledge_base_id`/`status` in process (`backend/agent/adapters/redis_store.py:81-110`).
- `GET /workflows` returns a flat list with no `total`/`has_more`/`next_cursor` (`backend/api/routers/workflows.py:19-39`).
- `WorkflowRunListResponse` has no pagination envelope.

### Acceptance Criteria
- [ ] Redis adapter maintains per-KB and per-`(kb, status)` sorted-set indexes; `list_runs` uses the narrowest available index.
- [ ] `WorkflowRunStoreProtocol.list_runs` returns a typed `PageResult[WorkflowRun]` with `items`, `next_cursor`, `has_more`.
- [ ] `WorkflowRunListResponse` carries `has_more` and `next_cursor`.
- [ ] `/workflows` accepts a `cursor` query param (mutually exclusive with `offset`).
- [ ] In-memory adapter implements the same protocol semantics.
- [ ] Tests: 10k runs, `limit=50` returns in <50ms in CI; cursor pagination round-trips.

### Verification
- `pytest backend/tests/agent/ backend/tests/api/test_workflows.py` green.
- Benchmark assertion in test: `list_runs` with 10k seed runs and `limit=50` returns ≤ 50ms on CI runner.

### Code touch points
- `backend/agent/adapters/protocols.py` (modify)
- `backend/agent/adapters/in_memory.py` (modify)
- `backend/agent/adapters/redis_store.py` (modify)
- `backend/agent/service.py` (modify)
- `backend/api/contracts.py` (modify)
- `backend/api/routers/workflows.py` (modify)
- `backend/tests/agent/test_redis_store.py` (modify)

---

## Story agent.12: Add stage-level execution policy (per-event timeouts, retry, fatal taxonomy)

**ID:** agent.12
**Status:** planned
**Prerequisites:** [events.04]
**Unblocks:** [analytics.24, analytics.25]
**Estimated size:** M

**As a** platform engineer,
**I need** per-stage retry, per-stage timeout, and a fatal-vs-retryable error taxonomy declared as policy,
**so that** a flaky monitoring evaluation does not get the same retry budget as a flaky LLM call, and known fatal errors short-circuit to DLQ instead of looping.

### Current State
- `RetryPolicy` is a single global model applied to every handler (`backend/agent/models.py:20-32`).
- `handle_risk_scored` and `handle_graph_updated_for_analytics` use ad-hoc `except` blocks that swallow errors with no policy declaration (`backend/agent/coordinator.py:1429-1475`).
- `run_handler_with_retry` always treats every `Exception` as retryable (`backend/agent/coordinator.py:2374-2381`).
- No mapping from event_type → `StagePolicy`.

### Acceptance Criteria
- [ ] `StagePolicy` model with `timeout_seconds`, `retry_policy`, `fatal_exception_types: tuple[type[BaseException], ...]`.
- [ ] `StagePolicyRegistry` keyed by `event_type`, fed from `AgentConfig` (cross-edge to `agent.10`).
- [ ] `run_handler_with_retry` enforces per-stage timeout via `asyncio.wait_for` and short-circuits to DLQ on declared fatal exception types.
- [ ] Ad-hoc `try/except continue` blocks in handlers replaced with raised typed errors classified by the registry.
- [ ] Tests: timeout exceeded → retry; fatal classification → straight to DLQ; retryable → respects per-stage retry count.

### Verification
- `pytest backend/tests/agent/test_coordinator.py -k policy` green.
- Coverage ≥ 85% on `agent/`.

### Code touch points
- `backend/agent/models.py` (modify)
- `backend/agent/policy.py` (new)
- `backend/agent/coordinator.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/agent/test_coordinator.py` (modify)

---

## Story agent.13: Formalize workflow definitions and dependency graph

**ID:** agent.13
**Status:** planned
**Prerequisites:** []
**Unblocks:** [analytics.12, analytics.21, api.24, embeddings.12]
**Estimated size:** M

**As a** platform engineer,
**I need** a registered catalog of `WorkflowDefinition`s declaring step dependencies (DAG), with validation at submission,
**so that** unknown step names are rejected at the API and the event→step mapping is not a module-private constant.

### Current State
- `WorkflowSubmissionRequest.requested_steps` is a free-form `list[str]` (`backend/agent/service_models.py`); no validation against a known step catalog.
- `_STEP_BY_EVENT_TYPE` and `_DEFAULT_STEP_SEQUENCE` are hardcoded module constants (`backend/agent/workflow_tracking.py:35-58`).
- `AgentService.start_workflow` calls `WorkflowStepState(step_name=...)` without verifying the name is known (`backend/agent/service.py:37-65`).

### Acceptance Criteria
- [ ] `WorkflowDefinition` model with `id`, `steps: tuple[WorkflowStepDef, ...]`, `dependencies: dict[str, tuple[str, ...]]`, `event_to_step: dict[str, str]`.
- [ ] `WorkflowDefinitionRegistry` provides catalog lookup; default Medicare flow registered.
- [ ] `WorkflowSubmissionRequest` references a `workflow_definition_id` and optional `step_overrides`; unknown step names raise `UnknownWorkflowStepError` at submission.
- [ ] `WorkflowEventTracker` consults the registry for step mapping instead of module constants.
- [ ] Tests: unknown definition → 400; unknown step → 400; valid definition → run executes end-to-end with same observable behavior as before.

### Verification
- `pytest backend/tests/agent/` green.
- Coverage ≥ 85% on `agent/`.

### Code touch points
- `backend/agent/definitions.py` (new)
- `backend/agent/models.py` (modify)
- `backend/agent/service_models.py` (modify)
- `backend/agent/service.py` (modify)
- `backend/agent/workflow_tracking.py` (modify)
- `backend/tests/agent/test_definitions.py` (new)

---

## Story agent.14: Add per-stage and per-KB concurrency limits / backpressure

**ID:** agent.14
**Status:** planned
**Prerequisites:** [_observability.04]
**Unblocks:** [analytics.21, analytics.22]
**Estimated size:** M

**As a** platform engineer,
**I need** per-stage and per-knowledge-base concurrency caps with backpressure and queue-depth metrics,
**so that** one noisy KB cannot saturate GNN or embedding stages for the whole tenant set.

### Current State
- `drain_ingestion_events` processes deliveries sequentially in one loop (`backend/agent/coordinator.py:2416-2530`).
- No semaphores, no per-stage concurrency knobs, no per-KB caps.
- No queue-depth, in-flight, or saturation metric is emitted from the coordinator.

### Acceptance Criteria
- [ ] `ConcurrencyController` model with per-stage `max_inflight` and per-KB `max_inflight` knobs, configured via `AgentConfig`.
- [ ] `drain_ingestion_events` dispatches handlers concurrently bounded by both stage and KB semaphores; over-cap deliveries are deferred (not ACKed) until capacity frees.
- [ ] Queue-depth, in-flight, and saturation counters emitted per stage + per KB (uses observability surface from `_observability.04`).
- [ ] Tests: cap=1 serializes per-KB; cap=N parallelizes; backpressure does not lose events.

### Verification
- `pytest backend/tests/agent/test_coordinator.py -k concurrency` green.
- Manual: enqueue 50 events for one KB, observe in-flight metric capped per config.

### Code touch points
- `backend/agent/concurrency.py` (new)
- `backend/agent/coordinator.py` (modify)
- `backend/config/schema.py` (modify)
- `backend/tests/agent/test_coordinator.py` (modify)

---

## Story agent.15: Production-harden the Redis workflow store

**ID:** agent.15
**Status:** planned
**Prerequisites:** []
**Unblocks:** []
**Estimated size:** M

**As a** platform engineer,
**I need** the Redis workflow store to use bounded timeouts, retries, a connection pool, optional TLS, schema versioning, and a `check_health()` surface,
**so that** a Redis blip does not hang the API and the store can be probed by readiness checks (cross-edge with `agent.09`).

### Current State
- `RedisWorkflowRunStore.__init__` takes URL + prefix only (`backend/agent/adapters/redis_store.py:19-37`); no connect/socket timeouts, retry policy, pool sizing, TLS validation.
- No schema-version field on persisted records (`backend/agent/models.py:79-99`).
- No `check_health()` method on the protocol or adapter (`backend/agent/adapters/protocols.py:11-49`).

### Acceptance Criteria
- [ ] `RedisWorkflowRunStore` accepts `connect_timeout`, `socket_timeout`, `retry_attempts`, `pool_max_connections`, `tls_verify`.
- [ ] `WorkflowRun` adds a `schema_version: int` field; reads tolerate older versions via a registered upgrader.
- [ ] `WorkflowRunStoreProtocol.check_health() -> StoreHealth` added; Redis adapter probes with a small `PING`/round-trip and returns latency.
- [ ] Defaults match production-safe values; documented in `backend/agent/README.md`.
- [ ] Tests: unreachable Redis → `check_health()` returns `unhealthy` within `connect_timeout`; schema migration round-trips an older payload.

### Verification
- `pytest backend/tests/agent/test_redis_store.py` green.
- Manual: stop Redis container, call `/ready`, observe 503 within timeout.

### Code touch points
- `backend/agent/adapters/redis_store.py` (modify)
- `backend/agent/adapters/protocols.py` (modify)
- `backend/agent/models.py` (modify)
- `backend/agent/README.md` (modify)
- `backend/tests/agent/test_redis_store.py` (modify)

---

## Story agent.16: Enforce RBAC, tenant/KB scoping, and metadata redaction across workflow ops

**ID:** agent.16
**Status:** planned
**Prerequisites:** [_security.04, _multitenancy.03]
**Unblocks:** [api.17]
**Estimated size:** M

**As a** security engineer,
**I need** every workflow-route operation gated by the policy registry with tenant/KB scope predicates, and request metadata redacted before it lands in logs,
**so that** analysts cannot read or cancel workflows outside their tenant and idempotency keys / error messages do not leak PII to operational logs.

### Current State
- Only `viewer` is enforced on `GET /workflows` (`backend/api/routers/workflows.py:22`).
- No cancellation/start/DLQ/history endpoints exist; no policy entries reserved for them.
- `AgentService.start_workflow` logs metadata verbatim — `metadata = dict(request.metadata)` (`backend/agent/service.py:49-50`) — and `failed_metadata["publish_error"] = str(exc)` (`backend/agent/service.py:84-86`) writes raw exception strings to the persisted record.
- No tenant/KB scope predicate on `list_workflows`.

### Acceptance Criteria
- [ ] Policy registry entries added for `workflows:list`, `workflows:read`, `workflows:start`, `workflows:cancel`, `workflows:dlq:*` per `_security.04`.
- [ ] `list_workflows` / `get_workflow_status` / `cancel_workflow` enforce `tenant_id` / `knowledge_base_id` scope predicates (cross-edge `_multitenancy.03`).
- [ ] Request metadata is redacted via a shared redactor before logging or persistence (allowlist of safe keys).
- [ ] Error messages from downstream subsystems are redacted (no raw `str(exc)` in logs or stored metadata for known-sensitive subsystems).
- [ ] Tests: tenant A cannot list/cancel tenant B's workflow; PII in metadata never appears in caplog output.

### Verification
- `pytest backend/tests/api/test_workflows.py backend/tests/agent/test_service.py` green.
- Coverage ≥ 85% on `agent/`, `api/routers/`.

### Code touch points
- `backend/api/routers/workflows.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/agent/service.py` (modify)
- `backend/agent/redaction.py` (new)
- `backend/tests/api/test_workflows.py` (modify)
- `backend/tests/agent/test_service.py` (modify)

---

## Story agent.17: Add workflow metrics, traces, and structured logs at the agent boundary

**ID:** agent.17
**Status:** planned
**Prerequisites:** [_observability.02, _observability.03]
**Unblocks:** [api.05, api.20]
**Estimated size:** M

**As an** SRE,
**I need** the agent module to emit submission/duration/retry/DLQ/cancellation counters, propagate the active trace through to the worker, and attach `correlation_id`+`workflow_id` to every log line,
**so that** a single workflow can be followed end-to-end across API and worker in Grafana/Jaeger.

### Current State
- The coordinator calls `observe_pipeline_stage` per stage (`backend/agent/coordinator.py:154`, used in handlers), but emits no agent-owned metrics for submissions, run durations, retries, DLQ publishes, cancellations, or recovery.
- `run_handler_with_retry` writes plain logger lines on retry/DLQ (`backend/agent/coordinator.py:2402-2412`) without metrics.
- `AgentService.start_workflow` does not start a span or bind correlation IDs (`backend/agent/service.py:37-100`).

### Acceptance Criteria
- [ ] Counters: `chili_workflow_submissions_total`, `chili_workflow_cancellations_total`, `chili_workflow_retries_total`, `chili_workflow_dlq_total`, `chili_workflow_recoveries_total` (labelled by `kb_id`, `event_type`).
- [ ] Histograms: `chili_workflow_run_duration_seconds`, `chili_workflow_stage_duration_seconds`.
- [ ] `AgentService.start_workflow` opens a span; the span context is propagated into the published event so the worker continues the trace.
- [ ] Every log line in `agent/` carries `workflow_id`, `correlation_id`, `kb_id` (via `bind_correlation_id`).
- [ ] Metrics surface unit-tested via the observability test fixtures.

### Verification
- `pytest backend/tests/agent/ backend/tests/observability/` green.
- Manual: trigger a workflow, view the trace in Jaeger end-to-end; confirm metrics counters increment in `/metrics`.

### Code touch points
- `backend/agent/coordinator.py` (modify)
- `backend/agent/service.py` (modify)
- `backend/agent/metrics.py` (new)
- `backend/agent/workflow_tracking.py` (modify)
- `backend/tests/agent/test_metrics.py` (new)

---

## Story agent.18: Add a Postgres-backed durable WorkflowRunStore adapter

**ID:** agent.18
**Status:** planned
**Prerequisites:** [database.03, database.07]
**Unblocks:** [agent.06, agent.20]
**Estimated size:** L

**As a** platform engineer,
**I need** a `PostgresWorkflowRunStore` implementing `WorkflowRunStoreProtocol` so workflow runs persist transactionally to Postgres,
**so that** audit-grade lifecycle storage (`agent.06`) has an authoritative durable backend and Redis can be treated as the cache it is.

### Current State
- The protocol exposes the full surface but only `InMemoryWorkflowRunStore` and `RedisWorkflowRunStore` exist (`backend/agent/adapters/protocols.py:11-49`, `backend/agent/adapters/redis_store.py`, `backend/agent/adapters/in_memory.py`).
- `create_workflow_run_store_from_env` only selects `in_memory` or `redis` (`backend/agent/adapters/runtime.py:18-31`).
- A `TODO(production)` comment in the protocol calls out Postgres + Redis as required (`backend/agent/adapters/protocols.py:23-24`).

### Acceptance Criteria
- [ ] `PostgresWorkflowRunStore` implementing all `WorkflowRunStoreProtocol` methods, using `ConnectionProvider` from `backend/database/`.
- [ ] Alembic migration creates `workflow_runs` and supporting indexes (correlation, idempotency, `(kb, status, created_at)`).
- [ ] `runtime.py` accepts `postgres` literal and resolves `ConnectionProvider` via `build_connection_provider`.
- [ ] All existing in-memory and Redis behavior tests are re-run against the Postgres adapter via a shared test contract.
- [ ] `check_health()` surface (per `agent.15`) implemented for Postgres adapter.

### Verification
- `pytest backend/tests/agent/test_postgres_store.py -m integration` green against a real Postgres instance.
- `pyright --strict` clean on `agent/adapters/`.
- Coverage ≥ 85% on `agent/`.

### Code touch points
- `backend/agent/adapters/postgres.py` (new)
- `backend/agent/adapters/runtime.py` (modify)
- `backend/agent/adapters/protocols.py` (modify)
- `backend/database/migrations/versions/<new>_workflow_runs.py` (new)
- `backend/tests/agent/test_postgres_store.py` (new)

---

## Story agent.19: Add start_workflow / cancel_workflow / DLQ-replay HTTP endpoints

**ID:** agent.19
**Status:** planned
**Prerequisites:** [agent.08, api.05]
**Unblocks:** [api.25]
**Estimated size:** M

**As an** analyst,
**I need** HTTP endpoints to submit, cancel, and replay workflow runs (and inspect their DLQ entries),
**so that** the SPA can drive the full workflow lifecycle without my SRE pasting Redis commands.

### Current State
- `backend/api/routers/workflows.py` only mounts `GET /workflows` (`backend/api/routers/workflows.py:1-39`).
- `AgentService.start_workflow` / `cancel_workflow` exist (`backend/agent/service.py:37-138`) but no router calls them.
- `DlqService` does not yet exist (`agent.08` creates it).

### Acceptance Criteria
- [ ] `POST /workflows` accepts `WorkflowSubmissionRequest`; returns `202` with `WorkflowSubmissionResponse`.
- [ ] `GET /workflows/{workflow_id}` returns full run; `404` when missing.
- [ ] `POST /workflows/{workflow_id}/cancel` returns the updated run; `409` if already terminal.
- [ ] `GET /workflows/{workflow_id}/dlq` and `POST /workflows/{workflow_id}/dlq/{entry_id}/replay|resolve|ignore` mounted, each gated by the policy registry (cross-edge `agent.16`).
- [ ] OpenAPI documents all new endpoints with error responses.
- [ ] Tests cover happy path + every error mapping.

### Verification
- `pytest backend/tests/api/test_workflows.py` green.
- Manual: `make dev`, `curl -X POST /workflows ... | curl /workflows/.../cancel` round-trip succeeds.

### Code touch points
- `backend/api/routers/workflows.py` (modify)
- `backend/api/contracts.py` (modify)
- `backend/api/dependencies.py` (modify)
- `backend/tests/api/test_workflows.py` (modify)

---

## Story agent.20: Add a production agent quality gate (multi-worker, crash recovery, retention, DLQ replay)

**ID:** agent.20
**Status:** planned
**Prerequisites:** [agent.05, agent.07, agent.08, agent.18, _cicd.05]
**Unblocks:** []
**Estimated size:** L

**As a** release captain,
**I need** a documented, automated quality-gate suite that exercises multi-worker concurrency, crash recovery, retention purge, and DLQ replay against real Redis + Postgres,
**so that** an agent release cannot ship unless those production behaviors actually work.

### Current State
- Unit coverage exists for handler paths, but no documented load/concurrency/crash-recovery suite (see existing `backend/tests/agent/test_coordinator.py` skeleton).
- Prior audit (Wave 1 epics) flagged a no-op test class body in `backend/tests/agent/test_coordinator.py` for the production-readiness profile — no integration profile gates a release.

### Acceptance Criteria
- [ ] New `backend/tests/agent/integration/test_production_gate.py` covers: (a) two workers consume the same stream without duplicates, (b) `SIGKILL` of one worker triggers reconciler recovery within configured lease window, (c) retention purge removes runs and indexes, (d) DLQ replay round-trips an event back into the pipeline.
- [ ] Suite marked `@pytest.mark.integration` and runs in CI under `_cicd.05` profile against Redis + Postgres + Neo4j containers.
- [ ] Documented runbook in `backend/agent/README.md` (`## Production Gate`) explains how to run locally.
- [ ] Coverage gate ≥ 85% on `agent/` remains enforced.

### Verification
- `pytest -m integration backend/tests/agent/integration/` green in CI.
- Coverage report shows the gate paths are covered, not just declared.

### Code touch points
- `backend/tests/agent/integration/test_production_gate.py` (new)
- `backend/tests/agent/conftest.py` (modify)
- `backend/agent/README.md` (modify)
- `.github/workflows/ci.yaml` (modify)
