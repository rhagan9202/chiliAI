# SAFE-CMS-002 Durable Score-All Workflows Implementation Plan

**Owner:** Codex
**Date:** 2026-08-02
**Branch:** `fix/normalize-kb-query-param`
**Parent dependency:** `SAFE-CMS-001` committed as `fb09656`

## Goal

Make KB-scoped score-all analytics durable, restartable, observable, and replayable without adding
investigator-facing operator controls into the Workbench.

## Architecture

Start with a domain-neutral score-run seam under analytics. Use the existing risk service's deterministic
`request_id` capability for idempotent per-entity scoring, and reuse the existing workflow/event patterns for
later API/worker integration. The first slice adds score-run and score-batch state models plus a repository
protocol and in-memory adapter; later slices wire this into service/API/UI surfaces.

## Task 1: Score Run And Batch State Repository

**Files:**
- Create: `backend/analytics/score_runs/models.py`
- Create: `backend/analytics/score_runs/protocols.py`
- Create: `backend/analytics/score_runs/adapters/in_memory.py`
- Test: `backend/tests/analytics/score_runs/test_in_memory.py`

- [x] **Step 1: Write failing repository tests**

Cover run creation, idempotency lookup, status/count updates, batch upsert/list, detached copies, and KB delete.

- [x] **Step 2: Implement models and in-memory repository**

Keep the repository independent from FastAPI and worker coordination.

- [x] **Step 3: Run focused repository tests**

Expected: score-run repository tests pass.

Task 1 review notes:

- Repository tests first failed with `ModuleNotFoundError` for the missing `analytics.score_runs` package.
- Added score-run and score-batch Pydantic models, repository protocol, package exports, and in-memory adapter.
- Initial implementation passed tests, then review found stale KB-scoped idempotency index entries when replacing
  the same run with a changed or cleared idempotency key. Added regression coverage and fixed index cleanup.
- Post-fix verification: `backend/tests/analytics/score_runs/test_in_memory.py -q` passed with 8 tests;
  `compileall backend/analytics/score_runs` and `git diff --check` passed.

## Task 2: Score-All Service Skeleton

**Files:**
- Create: `backend/analytics/score_runs/service.py`
- Test: `backend/tests/analytics/score_runs/test_service.py`

- [x] **Step 1: Write failing service tests**

Cover idempotent start, queued batch creation, cancel, replay-from-failed batches, and deterministic
per-entity request ids.

- [x] **Step 2: Implement minimal score-all service**

Do not execute heavy scoring in the API request. This slice should produce durable state and deterministic
work items.

- [x] **Step 3: Run focused service tests**

Expected: service tests pass.

Task 2 review notes:

- Service tests first failed with `ModuleNotFoundError` for the missing `analytics.score_runs.service` module.
- Added `ScoreRunService` plus `create_score_run_service` and `ScoreRunStartResult`.
- `start_score_all` is idempotent by KB-scoped key, creates queued batches, and leaves scoring execution for later
  workers.
- `cancel_run` cancels queued/running runs and unfinished batches while preserving completed batch state.
- `replay_failed_batches` creates a new queued run linked through `replay_of_run_id` and only requeues failed
  batch entity ids, so replay work remains pollable/cancelable like any other active run.
- Deterministic risk request ids use `risk:{run_id}:batch-{batch_number}:{entity_id}` for downstream
  risk-history idempotency.
- Post-implementation verification: `backend/tests/analytics/score_runs/test_service.py -q` passed with 7 tests;
  combined score-run repository/service tests passed with 15 tests; `compileall backend/analytics/score_runs` and
  `git diff --check` passed.

## Task 3: Event And API Surface

**Files:**
- Modify: `backend/events/types.py`
- Modify: `backend/events/codec.py`
- Modify: `backend/api/contracts.py`
- Create or modify: score-run API router/dependencies
- Test: focused event/API tests

- [x] **Step 1: Add score-run event contract tests**

Events should carry KB id, run id, status, counts, model/catalog versions, and replay lineage.

- [x] **Step 2: Add start/status/cancel/replay API tests**

Use direct route-function coverage if existing `TestClient` behavior hangs in this environment.

- [x] **Step 3: Implement routes and event publication**

Keep controls on KB operations/readiness surfaces, not investigator screens.

Task 3 review notes:

- Event codec test validates `score_run.status_changed` round trip with KB id, run id, status, counts,
  model/catalog versions, and replay lineage.
- Added optional score-run service event publication for start, cancel, and replay. Idempotent start retries
  return the existing run without publishing duplicate status events.
- Added KB-scoped routes under `/knowledgebases/{knowledge_base_id}/score-runs` for start, status, cancel,
  and replay, plus app registration and OpenAPI path/tag expectations.
- `TestClient` app/OpenAPI verification hangs in this environment, matching the earlier KB router limitation.
  Route registration was verified through direct router import.
- Focused verification passed: event/service/router command passed with 16 tests; targeted route-table import,
  `compileall`, and `git diff --check` passed.

## Task 4: Frontend Operations Status Slice

**Files:**
- Regenerate OpenAPI/frontend types.
- Add frontend API wrapper and focused KB operations UI test.

- [x] **Step 1: Add focused UI/API wrapper tests**
- [x] **Step 2: Implement minimal controls and run status display**
- [x] **Step 3: Run focused frontend tests and build**

Task 4 review notes:

- Regenerated backend OpenAPI and frontend schema after adding score-run API contracts.
- Added `chili_app/src/api/scoreRuns.ts` with KB-scoped list, detail, start, cancel, and replay wrappers plus
  React Query hooks.
- Added `ScoreRunStatusPanel` for score-all status, counts, model/catalog versions, replay lineage, batch state,
  and start/cancel/replay controls in the KB operations context rail.
- Initial review found Start was unreachable without a prior run and existing runs were undiscoverable after
  refresh. Fixed by allowing backend start requests to omit `entity_ids`, resolving the KB entity scope from the
  graph repository, adding `GET /knowledgebases/{knowledge_base_id}/score-runs`, and hydrating the UI from the
  latest durable run.
- Follow-up review found replay-created runs had queued batches but `replayed` run status, which would stop
  polling and block cancellation. Fixed replay-created runs to enter `queued` while preserving
  `replay_of_run_id`.
- Focused verification passed: backend score-run/event suite passed with 26 tests; frontend score-run/page suite
  passed with 47 tests; `pnpm build`, `git diff --check`, and backlog consistency passed.

## Task 5: Verification And Closeout

- [x] Backend focused tests.
- [x] Frontend focused tests/build if contracts changed.
- [x] `git diff --check`
- [x] `python3 scripts/backlog_consistency.py --check`
- [x] Update backlog and this plan with verification evidence.
