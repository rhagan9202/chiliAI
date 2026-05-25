# Agent Production Readiness Backlog - 2026-05-17

## Scope

This backlog covers the `backend/agent` module and the production behavior it owns:

- Workflow submission and lifecycle service in `backend/agent/service.py`
- Worker coordination and event dispatch in `backend/agent/coordinator.py`
- Workflow lifecycle projection in `backend/agent/workflow_tracking.py`
- Workflow run persistence adapters in `backend/agent/adapters`
- Worker health endpoint in `backend/agent/health.py`
- API integration through `backend/api/routers/workflows.py` and `backend/api/dependencies.py`

The goal is a production-ready agent module that can run multi-step ingestion, graph, analytics, monitoring, and structured-record workflows with durable state, clear operational semantics, safe retries, cancellation, observability, and strict verification gates.

## Current Baseline

- `AgentService` can create workflow runs, publish `agent.workflow.started`, list runs, return status, and mark runs cancelled.
- Workflow submissions support idempotency keys scoped by knowledge base, with conflict checks for trigger type, requested steps, and user metadata.
- The worker coordinator consumes domain events, dispatches handlers, wraps handlers with retry and DLQ routing, acknowledges processed deliveries, and shuts down gracefully on `SIGTERM` or `SIGINT`.
- `WorkflowEventTracker` updates workflow run and step status as events move through parse, chunk, extract, validate, graph, embedding, vector, readiness, and monitoring stages.
- Redis and in-memory workflow run stores exist. Redis is selectable with `CHILI_WORKFLOW_RUN_STORE_BACKEND=redis`.
- The worker exposes a lightweight `/health` endpoint based on last processed event time.
- The API exposes `GET /workflows` with viewer RBAC and projects workflow state into the frontend contract.
- Tests cover the main service paths, in-memory and Redis store behavior, workflow tracking, worker health, and many coordinator flows.

## Production Gaps

- API-facing agent service methods are synchronous even when called from async FastAPI routes.
- Cancellation is soft. A cancelled run is skipped only when a later event is tracked, not before every expensive handler stage.
- Idempotency keys and workflow state do not have a retention, expiration, archive, or cleanup policy.
- Redis workflow state updates are read-modify-write operations without compare-and-set semantics for concurrent worker/API updates.
- Workflow lookup by correlation ID scans recent runs instead of using an indexed store method.
- Redis listing reads the entire created-at index before applying filters and pagination.
- Workflow history is a mutable current-state projection, not an audit-grade lifecycle ledger.
- The workflow model is a list of requested step names, not a validated stage graph with dependencies, optional branches, and terminal conditions.
- DLQ publishing exists, but operator replay, resolution, and workflow-linked DLQ inspection are not agent-owned workflows.
- Worker readiness only tracks event recency and does not probe event bus, run store, storage, graph, vector, embedding, database, or downstream dependency health.
- Agent/worker configuration is spread across environment variables and event settings rather than a complete typed agent/worker config block.
- There are no explicit worker leases, heartbeats, stale-run recovery, or reconciliation jobs for runs left queued/running after process crashes.
- The production verification suite lacks load, concurrency, crash-recovery, and multi-worker race tests for the agent module.

## Priority Map

| Priority | Story | Outcome |
| --- | --- | --- |
| P0 | Stories 1-6 | Correct lifecycle, cancellation, durable state, indexed lookup, and safe concurrent updates |
| P1 | Stories 7-12 | Operational recovery, observability, readiness, DLQ operations, config, and API scalability |
| P2 | Stories 13-18 | Advanced workflow semantics, backpressure, deployment hardening, audit/export, and verification gates |

## Story 1: Add Async Agent Service Boundary

**As an API maintainer**, I need non-blocking workflow service methods so async FastAPI routes do not perform blocking persistence or event-publish work on the event loop.

### Current State

- `AgentServiceProtocol` exposes only synchronous methods.
- `GET /workflows` is an async route but calls `agent_service.list_workflows()` synchronously.
- Redis store operations and event bus publish calls are sync operations.

### Required Work

- Add async service protocol methods for:
  - `start_workflow_async`
  - `get_workflow_status_async`
  - `list_workflows_async`
  - `cancel_workflow_async`
- Provide an implementation strategy that keeps current sync tests and callers working:
  - Either implement native async adapters where dependencies support them.
  - Or use a bounded thread offload wrapper for sync adapters as an interim compatibility layer.
- Update API routes to use async methods when the injected service supports them.
- Add timeout and cancellation handling for async publish/persist operations.
- Preserve current sync `AgentServiceProtocol` compatibility until all API callers are migrated.

### Acceptance Criteria

- Async API routes do not call blocking Redis or event-bus operations directly.
- Existing sync service behavior remains available and covered by tests.
- New async service tests cover workflow start, list, status, cancellation, idempotency cache hits, idempotency conflicts, publish failure, and state-store failure.
- API route tests verify the async path is used for `/workflows`.
- Timeouts from store or event bus are converted to agent-layer errors with structured logs and no partial unhandled exceptions.
- Pyright strict mode reports no errors in modified agent and API files.

## Story 2: Enforce Hard Cancellation Before Expensive Work

**As an operator**, I need cancelling a workflow to stop future expensive work promptly so cancelled runs do not continue parsing, embedding, graph-writing, or analytics work.

### Current State

- `AgentService.cancel_workflow()` marks the run as `cancelled`.
- `WorkflowEventTracker.begin_event()` returns `False` for terminal runs.
- Handler-level cancellation checks are not enforced before each expensive stage.
- Events that do not resolve to a tracked workflow can still proceed.

### Required Work

- Add a cancellation guard that resolves workflow state before every dispatchable expensive operation.
- Make the guard explicit in `handle_event()` and in long-running handlers where one event can process many documents or assessments.
- Define behavior for cancellation discovered:
  - Before handler start: skip handler, acknowledge event, preserve cancelled state.
  - During batched handler work: stop before the next unit of work, record partial progress metadata, and do not emit downstream events for unfinished items.
- Ensure cancellation checks use indexed lookup by workflow ID or correlation ID once Story 4 is implemented.
- Add structured log fields for cancellation skips: workflow ID, correlation ID, event type, step name, and processed count.

### Acceptance Criteria

- A cancelled workflow does not call ingestion, chunking, extraction, validation, graph, embedding, vector, monitoring, analytics, or records handlers after cancellation is observed.
- Batched handlers stop between items and do not emit downstream events for unprocessed items.
- Cancelled events are acknowledged only after the cancellation state is recorded.
- Tests cover cancellation before dispatch, cancellation during a multi-document batch, cancellation for fallback-created runs, and cancellation when the run cannot be found.
- The workflow remains `cancelled`; tracker completion or failure paths cannot overwrite it.

## Story 3: Add Workflow Retention, Archival, and Idempotency TTL

**As a platform operator**, I need bounded workflow state retention so Redis and future durable stores do not grow without limit and idempotency keys have documented replay windows.

### Current State

- Idempotency keys are stored indefinitely.
- Workflow runs are stored indefinitely unless explicitly deleted.
- There is no typed configuration for retention windows.

### Required Work

- Add agent workflow retention configuration:
  - Active run retention
  - Terminal run retention
  - Idempotency key retention
  - Archived history retention
  - Cleanup batch size and cadence
- Extend `WorkflowRunStoreProtocol` with cleanup or expiry methods.
- Implement Redis TTL behavior for:
  - Workflow JSON keys
  - Idempotency keys
  - Correlation indexes
  - Created-at indexes
- Add cleanup for stale sorted-set members.
- Define policy for repeated idempotency keys after TTL expiry.
- Document operator guidance for retention choices by environment.

### Acceptance Criteria

- Redis keys created by the workflow run store have appropriate TTLs when configured.
- Cleanup removes stale index entries without deleting active runs.
- Expired idempotency keys allow new submissions only after the configured replay window.
- Terminal run retention keeps enough data for workflow UI and support investigations.
- Unit tests cover TTL assignment, cleanup, stale index removal, idempotency expiry, and disabled-retention mode.
- Documentation describes default retention values and operational tradeoffs.

## Story 4: Add Indexed Workflow Lookup by Correlation ID

**As a worker maintainer**, I need workflow tracking to find runs by correlation ID without scanning recent workflow records.

### Current State

- `WorkflowEventTracker._find_by_correlation_id()` calls `list_runs(limit=1000)` and scans metadata.
- Redis `list_runs()` retrieves the full created-at index before filtering.
- Correlation ID is stored in run metadata but is not a first-class lookup key.

### Required Work

- Add `find_by_correlation_id(correlation_id: str) -> WorkflowRun | None` to `WorkflowRunStoreProtocol`.
- Add correlation indexing in in-memory and Redis stores.
- Maintain the index on save, update, and delete.
- Backfill or lazily repair missing index entries for existing runs.
- Update `WorkflowEventTracker` to use the indexed lookup method.
- Add index key namespacing and retention behavior consistent with Story 3.

### Acceptance Criteria

- Tracking an event performs an indexed lookup rather than scanning `list_runs()`.
- Correlation index entries are updated when metadata changes and removed when runs are deleted.
- Fallback run creation remains available when no correlation match exists.
- Tests cover lookup hits, misses, metadata changes, delete cleanup, fallback creation, and Redis key behavior.
- Performance tests show correlation lookup remains stable with at least 10,000 workflow runs.

## Story 5: Make Workflow Store Updates Race-Safe

**As a platform engineer**, I need workflow state transitions to be atomic under multiple workers and API calls so cancellation, failure, and completion cannot overwrite each other incorrectly.

### Current State

- Redis `update_run()` loads a run, merges updates in process memory, and saves the whole record.
- The tracker prevents terminal overwrites only based on the loaded copy.
- Concurrent updates can race between API cancellation and worker completion/failure.
- Status transition rules are implicit in service and tracker code.

### Required Work

- Define an explicit workflow status transition table.
- Add store-level atomic conditional update support, such as:
  - Expected current status or version
  - Monotonic version number
  - Redis transaction or Lua script for compare-and-set updates
- Add `WorkflowRun.version` or equivalent revision metadata.
- Update service and tracker paths to use conditional transitions.
- Make terminal statuses final at the store layer.
- Ensure index updates and workflow JSON writes happen atomically.

### Acceptance Criteria

- `cancelled`, `completed`, and `failed` runs cannot be overwritten by stale worker updates.
- Concurrent API cancellation and worker completion produces one valid terminal state according to documented precedence.
- Store update methods return a clear conflict result or exception when expected status/version does not match.
- Redis implementation updates workflow payload and indexes atomically.
- Tests simulate concurrent cancellation/completion/failure and verify deterministic outcomes.
- In-memory store follows the same transition rules as Redis.

## Story 6: Add Audit-Grade Workflow History

**As a support engineer**, I need an immutable workflow lifecycle history so incidents can be reconstructed after the current workflow state has changed.

### Current State

- `WorkflowRun` stores only current status, current step states, timestamps, and metadata.
- `WorkflowEventTracker` updates state in place.
- Architecture notes call out audit-grade workflow history as remaining production work.

### Required Work

- Introduce a `WorkflowRunEvent` or `WorkflowLifecycleRecord` model containing:
  - Workflow ID
  - Knowledge base ID
  - Correlation ID
  - Event type
  - Step name
  - Previous status and next status
  - Timestamp
  - Actor/source
  - Error details when applicable
  - Worker identity when applicable
- Extend store protocol with append/read lifecycle history methods.
- Persist history records for submit, publish, begin step, complete step, fail step, cancel, retry exhaustion, DLQ publish, replay, and cleanup.
- Keep current-state projection as a derived operational view.
- Add API/read-model support for fetching history when authorized.

### Acceptance Criteria

- Every workflow lifecycle transition appends an immutable history record.
- Current state can be reconstructed from lifecycle records in tests.
- History append and current-state update are atomic or have a reconciliation strategy.
- Support users can retrieve workflow history by workflow ID with RBAC.
- Error records redact sensitive values but preserve enough context for diagnosis.
- Tests cover normal completion, failure, cancellation, DLQ routing, replay, and cleanup history.

## Story 7: Add Worker Heartbeats, Leases, and Stale Run Recovery

**As an operator**, I need the system to detect crashed workers and recover queued or running workflows without manual database edits.

### Current State

- Worker health tracks only last successfully processed event in memory.
- Workflow runs can remain `queued` or `running` if the API or worker crashes at the wrong time.
- Redis consumer groups retain pending entries, but agent workflow state does not include leases or worker ownership.

### Required Work

- Add worker identity to runtime configuration.
- Add workflow lease metadata:
  - Worker ID
  - Lease acquired timestamp
  - Lease expiry
  - Last heartbeat
  - Current event delivery ID when available
- Renew leases during long-running work.
- Add a reconciliation job that:
  - Finds stale queued/running workflows.
  - Inspects event bus pending entries where supported.
  - Marks unrecoverable runs failed with reason.
  - Requeues recoverable work or releases stale leases.
- Record recovery actions in workflow history.

### Acceptance Criteria

- A worker crash during a running workflow is detected after the configured lease timeout.
- Stale running workflows are either resumed, requeued, or failed according to documented rules.
- Recovery is idempotent and safe with multiple worker replicas.
- Heartbeat state is visible through health/readiness output.
- Tests cover lease acquisition, renewal, expiry, recovery, duplicate recovery attempts, and pending event reconciliation.

## Story 8: Build DLQ Inspection, Replay, and Resolution Workflows

**As an operator**, I need first-class dead-letter operations so failed events can be inspected, replayed, or marked resolved without ad hoc Redis access.

### Current State

- `run_handler_with_retry()` publishes to DLQ after retry exhaustion.
- DLQ records are event-bus owned.
- The agent tracker marks the workflow failed through the `on_failure` callback.
- There is no agent service API for DLQ list/replay/resolve.

### Required Work

- Define a DLQ read model tied to workflow ID, correlation ID, event type, retry count, failure time, and error class.
- Add agent service operations:
  - List DLQ entries
  - Get DLQ entry detail
  - Replay DLQ entry
  - Mark DLQ entry resolved
  - Mark DLQ entry ignored with reason
- Implement replay as a workflow operation with idempotency protection.
- Preserve original event payload and append replay metadata.
- Add RBAC policy for DLQ operations separate from viewer access.
- Add audit history records for replay and resolution actions.

### Acceptance Criteria

- Operators can list DLQ entries filtered by workflow ID, KB, event type, status, and time range.
- Replaying a DLQ entry re-publishes the original event with replay metadata and does not duplicate already-completed workflow steps.
- Resolved and ignored DLQ entries are not replayed accidentally.
- Replay failures create new DLQ/history records without deleting original evidence.
- Tests cover list, detail, replay, duplicate replay prevention, resolve, ignore, RBAC denial, and audit history.

## Story 9: Strengthen Worker Readiness and Dependency Health

**As an SRE**, I need health and readiness endpoints that reflect whether the worker can actually process events.

### Current State

- Worker `/health` returns `ok` or `degraded` based on event recency.
- Health startup failure is logged and does not abort the worker.
- There is no readiness endpoint.
- Dependency connectivity is not probed from the worker health server.

### Required Work

- Split liveness and readiness semantics:
  - `/health` for process liveness
  - `/readiness` for dependency readiness
  - `/metrics` if metrics are served from the same process
- Add dependency checks for:
  - Event bus consume/publish capability
  - Workflow run store read/write capability
  - Object store
  - Graph repository
  - Vector store
  - Embedding provider
  - Database-backed analytics stores when configured
- Include worker identity, consumer group, consumer name, current lease count, last processed event, and last error summary.
- Ensure checks have short timeouts and never hang the health server.
- Return Kubernetes-friendly status codes.

### Acceptance Criteria

- `/health` remains fast and returns process liveness.
- `/readiness` returns non-200 when required dependencies are unavailable.
- Dependency check failures are reported with subsystem names and redacted errors.
- Readiness tests cover all-healthy, one dependency failing, timeout, skipped optional dependency, and Redis unavailable.
- Health responses do not expose credentials or full URLs containing secrets.

## Story 10: Add Production Worker Configuration Model

**As a deployer**, I need all agent and worker behavior configured through typed settings with documented environment mappings.

### Current State

- `HealthSettings` and `RetryPolicy` are typed in agent models.
- Event bus settings exist outside the agent module.
- Workflow store backend is selected through `CHILI_WORKFLOW_RUN_STORE_BACKEND`.
- Worker behavior such as health port, retry policy, retention, leases, concurrency, and cleanup cadence is not centralized.

### Required Work

- Add `AgentConfig` or `WorkerConfig` to the domain configuration schema.
- Include:
  - Workflow run store backend
  - Retention windows
  - Retry policy
  - Health/readiness settings
  - Worker identity/prefix
  - Lease and heartbeat intervals
  - Poll batch size overrides where appropriate
  - Per-stage concurrency limits
  - DLQ replay policy
- Wire config through `build_worker_dependencies()` and API dependency factories.
- Update default config files and environment documentation.
- Add production-mode guardrails for unsafe in-memory stores.

### Acceptance Criteria

- All agent/worker operational settings are represented in typed config with validation.
- Defaults preserve current local development behavior.
- Production config can reject in-memory workflow store and in-memory event bus unless explicitly allowed.
- Tests cover config defaults, invalid values, environment overrides, and runtime wiring.
- Operator docs list every supported agent/worker setting and example production values.

## Story 11: Scale Workflow Listing and Filtering

**As a UI and API maintainer**, I need workflow listing to stay fast as the number of runs grows.

### Current State

- Redis `list_runs()` reads all workflow IDs from the created-at sorted set, loads each run, then filters by KB and status in process.
- API `/workflows` does not expose query parameters for filtering or pagination.
- The frontend projection receives a default unfiltered list.

### Required Work

- Add store indexes for:
  - Knowledge base ID
  - Status
  - Knowledge base plus status
  - Created-at pagination
- Implement bounded Redis range queries for common filters.
- Add API query parameters for `knowledge_base_id`, `status`, `limit`, and `offset` or cursor.
- Consider cursor pagination to avoid unstable offset pagination under concurrent inserts.
- Add total count or `has_more` metadata if required by the UI.

### Acceptance Criteria

- Listing workflows does not scan all workflow records for common filters.
- API supports filter and pagination parameters with validation and RBAC.
- Existing unfiltered `/workflows` behavior remains compatible.
- Tests cover filter combinations, pagination bounds, stable ordering, invalid params, and large Redis data sets.
- Performance tests verify bounded calls for at least 50,000 workflow runs.

## Story 12: Add Stage-Level Timeouts, Budgets, and Retry Policy

**As an operator**, I need retry and timeout behavior tuned per workflow stage so a slow or failing dependency does not stall the whole worker indefinitely.

### Current State

- `RetryPolicy` is global for handler retries.
- Individual handlers may call downstream services without agent-owned timeout budgets.
- Some secondary handlers catch exceptions to avoid blocking primary flow, but that behavior is not expressed as policy.

### Required Work

- Add per-stage execution policy:
  - Timeout
  - Retry count
  - Backoff
  - Jitter
  - Retryable error classes
  - Fatal error classes
  - Whether failure blocks downstream stages
- Apply policy to handlers in `coordinator.py`.
- Record stage attempts and timeout failures in workflow metadata/history.
- Add structured error categories for downstream services.
- Ensure retry behavior remains idempotent for replay-safe handlers.

### Acceptance Criteria

- Each event type has a configured or default execution policy.
- Timeouts mark the stage failed or degraded according to policy and route to DLQ when appropriate.
- Non-blocking secondary analytics failures are represented explicitly in policy.
- Tests cover retryable failures, fatal failures, timeout, jitter bounds, secondary handler isolation, and DLQ routing.
- Logs and history include attempt number, policy name, and final outcome.

## Story 13: Formalize Workflow Definitions and Dependency Graphs

**As a product engineer**, I need workflow definitions to describe valid stages, dependencies, branches, and terminal conditions instead of relying on free-form requested step names.

### Current State

- `WorkflowSubmissionRequest.requested_steps` is `list[str]`.
- `WorkflowRun` requires at least one unique step name but does not validate known steps.
- `WorkflowEventTracker` has hardcoded event-to-step and default sequence mappings.
- The architecture calls the agent a custom async state machine and leaves room for a workflow framework if complexity grows.

### Required Work

- Define workflow templates for:
  - Document ingestion
  - Graph build
  - Structured records ingestion
  - Analytics/risk scoring
  - Monitoring/alerts
  - Rebuild/reindex operations
- Model steps as typed definitions with:
  - Step ID
  - Event type
  - Dependencies
  - Optional/required flag
  - Retry policy key
  - Cancellation behavior
  - Terminal success conditions
- Validate submissions against known workflow templates.
- Derive tracker mapping from workflow definitions instead of hardcoded dictionaries.
- Define compatibility behavior for old free-form submissions during migration.

### Acceptance Criteria

- Unknown workflow steps are rejected at submission time with clear validation errors.
- Tracker mappings are generated from registered workflow definitions.
- Branching and optional stages can be represented without changing tracker code.
- Existing tests for current workflows continue to pass through compatibility mappings.
- New tests cover valid templates, invalid steps, branch completion, optional skipped steps, and terminal conditions.

## Story 14: Add Backpressure and Concurrency Controls

**As an SRE**, I need the worker to limit concurrent work by stage and knowledge base so downstream services are protected under load.

### Current State

- The worker drains batches and processes deliveries sequentially in the current loop.
- Horizontal scaling relies on Redis consumer groups.
- There are no per-stage or per-KB concurrency limits.

### Required Work

- Add configurable concurrency limits:
  - Global worker concurrency
  - Per event type/stage
  - Per knowledge base
  - Per downstream dependency where useful
- Add backpressure behavior when limits are reached:
  - Defer acknowledgement until work completes.
  - Avoid polling too aggressively when saturated.
  - Preserve fair scheduling across KBs.
- Expose queue depth, in-flight count, saturation, and wait time metrics.
- Add safeguards for memory growth from large batches.

### Acceptance Criteria

- Worker concurrency can be configured without code changes.
- Per-KB limits prevent one KB from starving all others.
- Saturation does not drop or prematurely acknowledge events.
- Tests cover global limit, per-stage limit, per-KB fairness, saturation, and graceful shutdown with in-flight tasks.
- Load tests demonstrate stable memory and throughput under sustained event volume.

## Story 15: Production-Harden Redis Workflow Store

**As a platform engineer**, I need Redis workflow state storage to be resilient, observable, and safe for multi-environment deployments.

### Current State

- Redis store accepts a URL and optional key prefix.
- It uses JSON values and sorted sets for current state.
- It does not expose health checks, retries, connection pool configuration, TLS/auth validation, or schema versioning.

### Required Work

- Add Redis client configuration:
  - Socket/connect timeouts
  - Retry policy
  - Connection pool sizing
  - TLS support
  - Key prefix from environment/config
  - Database selection guidance
- Add `check_health()` or store health protocol integration.
- Version workflow records and support migration/compatibility checks.
- Add namespaced keys for environment and tenant isolation if needed.
- Add robust error translation from Redis exceptions to agent exceptions.

### Acceptance Criteria

- Redis connection behavior is fully configurable and documented.
- Redis failures are surfaced as agent state-store errors with safe messages.
- Store health check verifies read/write/delete or a non-mutating equivalent.
- Workflow record version mismatches are detected and reported.
- Tests cover Redis timeout, unavailable Redis, malformed stored JSON, version mismatch, key prefix isolation, and health check success/failure.

## Story 16: Secure Workflow Operations and Data Exposure

**As a security reviewer**, I need workflow APIs and logs to enforce RBAC and avoid leaking sensitive workflow metadata.

### Current State

- `/workflows` requires the `viewer` role.
- Workflow metadata can contain arbitrary user metadata.
- DLQ and history APIs do not exist yet.
- Logs include errors from exceptions and may include downstream messages.

### Required Work

- Define role requirements for:
  - List workflows
  - View one workflow
  - Start workflow
  - Cancel workflow
  - Replay DLQ entry
  - View history
  - View error details
- Add metadata redaction for API responses, logs, history, and DLQ records.
- Add tenant/knowledge-base scoping where the auth model supports it.
- Ensure idempotency keys are not logged in full.
- Add security tests for unauthorized, wrong-role, and wrong-scope access.

### Acceptance Criteria

- Every workflow operation has an explicit policy registry entry.
- Sensitive fields are redacted consistently across logs, API responses, DLQ records, and history.
- Users cannot list or inspect workflows outside their authorized scope.
- Idempotency keys are hashed or truncated in logs and audit records.
- Tests cover RBAC, tenant scoping, metadata redaction, and denied cancellation/replay.

## Story 17: Add Workflow Metrics, Tracing, and Structured Logs

**As an operator**, I need enough telemetry to diagnose workflow latency, failure rate, retry pressure, and bottlenecks in production.

### Current State

- Coordinator uses pipeline spans and stage observation helpers.
- Worker logs key retry and shutdown events.
- Architecture documents desired metrics such as `pipeline_events_processed_total`.
- Agent-specific workflow metrics are incomplete.

### Required Work

- Add metrics for:
  - Workflow submissions by trigger and status
  - Workflow duration by workflow type
  - Step duration by event type
  - Retries by event type and error class
  - DLQ publishes
  - Cancellations
  - Stale run recoveries
  - Store operation latency
  - Correlation lookup misses
  - Worker in-flight counts and saturation
- Add trace attributes for workflow ID, correlation ID, KB ID, event type, step name, and worker ID.
- Use safe cardinality rules for labels.
- Standardize structured logs for submit, publish, begin, complete, fail, cancel, retry, DLQ, replay, and cleanup.

### Acceptance Criteria

- Agent metrics are emitted with documented names, labels, and cardinality constraints.
- Workflow traces connect API submission to worker processing through correlation ID.
- Logs contain enough structured fields to reconstruct a workflow without searching raw payloads.
- Tests or telemetry fixtures verify metric increments for success, failure, retry, DLQ, and cancellation paths.
- No metric labels include unbounded values such as raw idempotency keys or error messages.

## Story 18: Production Verification and Quality Gates

**As a release owner**, I need repeatable quality gates that prove the agent module is safe to promote to production.

### Current State

- Unit tests cover many service, store, tracker, health, and coordinator flows.
- Prior audit identified a no-op test class body in `backend/tests/agent/test_coordinator.py`.
- There is no dedicated production readiness test profile for multi-worker concurrency, crash recovery, or long-running workflows.

### Required Work

- Add a focused agent quality gate:
  - Unit tests
  - Integration tests with Redis event bus and Redis workflow store
  - API route tests
  - Multi-worker concurrency tests
  - Cancellation and crash-recovery tests
  - DLQ replay tests
  - Retention cleanup tests
  - Load/performance smoke tests
- Remove or replace no-op tests with meaningful coverage.
- Add strict typing coverage for the agent module and tests.
- Add coverage threshold specific to agent code.
- Add CI job documentation for running the production readiness suite.

### Acceptance Criteria

- `backend/agent` and `backend/tests/agent` are included in strict pyright scope.
- Agent test coverage meets or exceeds the project production gate.
- Redis-backed integration tests run in CI or an equivalent required environment.
- Multi-worker tests prove no stale overwrite of cancellation/failure/completion.
- Crash-recovery tests prove stale queued/running workflows are reconciled.
- The production readiness suite has a documented command and expected runtime.

## Suggested Execution Order

1. Story 5: race-safe workflow store updates.
2. Story 4: indexed correlation lookup.
3. Story 2: hard cancellation enforcement.
4. Story 3: retention, archival, and idempotency TTL.
5. Story 6: audit-grade workflow history.
6. Story 7: leases, heartbeats, and stale run recovery.
7. Story 9: worker readiness and dependency health.
8. Story 10: production worker configuration model.
9. Story 11: scalable workflow listing and filtering.
10. Story 1: async agent service boundary.
11. Story 12: stage-level timeouts and retry policy.
12. Story 8: DLQ inspection, replay, and resolution workflows.
13. Story 17: workflow metrics, tracing, and structured logs.
14. Story 16: secure workflow operations and data exposure.
15. Story 13: formal workflow definitions and dependency graphs.
16. Story 14: backpressure and concurrency controls.
17. Story 15: production-harden Redis workflow store.
18. Story 18: production verification and quality gates.

## Definition of Production Ready

The agent module is production ready when all of the following are true:

- Workflow state transitions are atomic, race-safe, and terminal states cannot be overwritten by stale updates.
- Cancellation prevents future expensive work and is observable in workflow history.
- Workflow lookup and listing are indexed and scale to production run volumes.
- Workflow state, idempotency keys, indexes, and history have explicit retention and cleanup behavior.
- Worker crashes are detected and stale queued/running workflows are recovered or failed deterministically.
- DLQ entries can be inspected, replayed, resolved, and audited through supported service/API workflows.
- Worker liveness and readiness accurately reflect process state and required dependency health.
- Agent and worker behavior is configured through typed, documented production settings.
- Workflow APIs enforce RBAC, tenant/KB scope, and metadata redaction.
- Metrics, traces, and structured logs cover submission, dispatch, retries, failures, cancellation, replay, and recovery.
- Redis-backed and multi-worker integration tests pass in CI.
- Strict typing and module coverage gates include `backend/agent` and `backend/tests/agent`.
