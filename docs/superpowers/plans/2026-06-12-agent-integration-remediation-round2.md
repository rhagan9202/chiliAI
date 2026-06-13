# Agent Integration Remediation Round 2

## Context

This plan covers the eight issues from the latest agent module and integration review. The repository already contains earlier fixes for workflow tracking, Redis runtime selection, typing, and focused test coverage. Do not revert unrelated working-tree changes.

## Execution Model

Work is split by issue. Each issue gets a subagent with this plan plus a scoped task. Agents should use test-driven development where practical, edit only the files needed for their issue, run focused tests, and return changed files plus verification output. The coordinator reviews each returned diff and sends revisions back before accepting.

Because several issues touch the same stores and coordinator paths, dispatch in waves:

1. Wave 1: Issue 1, Issue 2, Issue 8.
2. Wave 2: Issue 3, Issue 7.
3. Wave 3: Issue 4, Issue 5.
4. Wave 4: Issue 6.

Run `uv run --project backend pyright` and focused pytest after all accepted changes.

## Issue 1: Production Compose Still Defaults to In-Memory Agent Runtime

Priority: P0

Problem:
`docker-compose.yaml` now supplies `REDIS_URL`, but the event bus and workflow run store still default to in-memory because selectors are not set. `backend/events/runtime.py` defaults `CHILI_EVENT_BUS_BACKEND` to `in-memory`, and `backend/agent/adapters/runtime.py` defaults `CHILI_WORKFLOW_RUN_STORE_BACKEND` to `in_memory`.

Plan:

1. Add `CHILI_EVENT_BUS_BACKEND=${CHILI_EVENT_BUS_BACKEND:-redis}` and `CHILI_WORKFLOW_RUN_STORE_BACKEND=${CHILI_WORKFLOW_RUN_STORE_BACKEND:-redis}` to the `api` and `worker` service environments in `docker-compose.yaml`.
2. Add the same selectors to `.env.example` with Redis defaults so local Docker users see the intended production-like setup.
3. Add a regression test that loads `docker-compose.yaml` and `.env.example` and asserts the `api` and `worker` services include the Redis backend selectors and `REDIS_URL`.
4. Keep existing runtime tests intact.

Focused verification:

`uv run --project backend pytest backend/tests/config/test_docker_compose_agent_runtime.py backend/tests/agent/test_runtime.py -q`

## Issue 2: Stage Timeouts Can Duplicate Side Effects

Priority: P0

Problem:
`backend/agent/coordinator.py` runs synchronous handlers with `asyncio.wait_for(asyncio.to_thread(...), timeout=...)`. If a sync handler times out, the background thread keeps running while retry starts another execution, so side effects can duplicate.

Plan:

1. Add a regression test in `backend/tests/agent/test_coordinator.py` showing a timed-out synchronous handler is not retried concurrently.
2. Change retry behavior so a stage timeout is treated as terminal for that message attempt. It should write a DLQ entry and avoid launching another handler invocation.
3. Preserve retry behavior for ordinary retryable exceptions.
4. Make the test assert call count remains one, the DLQ has the timed-out event, and processing does not report success.

Focused verification:

`uv run --project backend pytest backend/tests/agent/test_coordinator.py -q`

## Issue 3: Redis save_run Can Poison Idempotency Indexes

Priority: P0

Problem:
`backend/agent/adapters/redis_store.py` claims idempotency before correlation. If correlation claim raises, the idempotency key can remain mapped to an unsaved workflow id.

Plan:

1. Add a Redis store regression test using the existing fake Redis setup: save a run with a correlation id, then attempt another run with the same correlation and a new idempotency key, assert the save raises, and assert the idempotency key was not left behind.
2. Verify that the same idempotency key can subsequently be used for a different valid run after the failed save.
3. Fix `save_run` so any idempotency key claimed by the current call is rolled back if a later uniqueness claim fails before the run is persisted.
4. Do not delete a pre-existing idempotency key owned by another run.

Focused verification:

`uv run --project backend pytest backend/tests/agent/test_redis_workflow_run_store.py -q`

## Issue 4: Redis list_runs Can Hide Valid Workflows Behind Stale Index Entries

Priority: P1

Problem:
`RedisWorkflowRunStore.list_runs` reads `limit + 1` ids, then drops stale or mismatched entries. A stale id near the top of an index can produce short or empty pages even when valid runs exist later.

Plan:

1. Add a regression test that places stale ids ahead of valid ids in a Redis index and asserts `list_runs(limit=1)` still returns the newest valid run and a correct `has_more`/`next_offset`.
2. Update Redis listing to scan index windows until it has enough valid runs for the requested page or the index is exhausted.
3. Compute `next_offset` from the scanned index position, not from the surviving run count.
4. Remove stale index entries opportunistically when the referenced run record is missing.
5. Preserve status and knowledge-base filters.

Focused verification:

`uv run --project backend pytest backend/tests/agent/test_redis_workflow_run_store.py -q`

## Issue 5: Workflow Scope Filtering Happens After Pagination

Priority: P1

Problem:
`backend/api/routers/workflows.py` fetches a page from the store and then filters inaccessible workflows. A user can receive an empty or short page with `has_more=true` when inaccessible workflows occupy the selected slice.

Plan:

1. Add a router regression test where an inaccessible newer workflow precedes an accessible older workflow and a viewer asks for `limit=1`; the response should include the accessible workflow instead of an empty page.
2. Update workflow listing so it keeps fetching underlying store pages until it fills the requested page with accessible workflows or the store is exhausted.
3. Return the store offset needed to continue scanning, not an offset based only on accessible items.
4. Keep admin behavior unchanged.
5. Avoid infinite loops if the store returns an empty page with `has_more=true`.

Focused verification:

`uv run --project backend pytest backend/tests/api/test_workflows_router.py -q`

## Issue 6: Realtime SSE Workflow Counts Are Capped and Unscoped

Priority: P1

Problem:
`backend/api/routers/events.py` computes active workflow counts from a single `limit=500` query and does not scope by viewer access, so counts can be incomplete and can expose activity from inaccessible knowledge bases.

Plan:

1. Add tests in `backend/tests/api/test_events_router.py` for active workflow counts beyond the first page and for a viewer scoped to one knowledge base.
2. Add user dependency to the event stream path if needed and filter counts with the same knowledge-base access rules used by workflow listing.
3. Page through queued/running workflows until the store is exhausted, accumulating counts after access checks.
4. Keep admins able to see all counts.
5. Avoid blocking the SSE stream startup on large unbounded single calls; use bounded pages.

Focused verification:

`uv run --project backend pytest backend/tests/api/test_events_router.py -q`

## Issue 7: Stage Policy Hooks Are Not Runtime-Configured

Priority: P2

Problem:
`drain_ingestion_events` accepts a `StagePolicyRegistry`, but the worker runtime never constructs one from environment or configuration, so stage-specific retry/timeout policy is effectively test-only.

Plan:

1. Add a config loader for stage policies, preferably in `backend/agent/policy.py`, that parses a JSON environment variable such as `CHILI_STAGE_POLICY_JSON`.
2. Supported JSON shape should map event type to policy fields: `max_retries`, `backoff_seconds`, `timeout_seconds`, and optionally `fatal_exception_types`.
3. Wire `run_worker` through to build and pass a registry into `drain_ingestion_events`.
4. Add tests for valid parsing, invalid JSON/unknown fields failing clearly, and worker drain using the configured timeout/retry values.
5. Preserve current defaults when the env var is absent.

Focused verification:

`uv run --project backend pytest backend/tests/agent/test_coordinator.py backend/tests/agent/test_policy.py -q`

## Issue 8: Correlation Adoption Skips Request-Shape Validation

Priority: P2

Problem:
`AgentService.start_workflow` returns an existing workflow by correlation id before validating that the new request matches the original workflow shape. A caller can accidentally reuse a correlation id for another knowledge base, trigger type, or incompatible request and get the wrong workflow.

Plan:

1. Add service tests for same correlation with different knowledge base, different trigger event type, and mismatched idempotency key.
2. Keep adoption behavior for matching requests.
3. Validate the existing workflow against the new request before returning it from the correlation path.
4. Raise an existing conflict/configuration exception with a clear message when the request does not match.
5. Do not change the idempotency-key-first behavior for exact idempotent retries.

Focused verification:

`uv run --project backend pytest backend/tests/agent/test_service.py -q`

## Final Verification

After all subagent work is accepted:

1. `uv run --project backend pyright`
2. `uv run --project backend pytest backend/tests/agent backend/tests/api/test_workflows_router.py backend/tests/api/test_events_router.py backend/tests/api/test_records_router.py backend/tests/api/test_workflow_projection.py -q`
3. `git diff --check`
