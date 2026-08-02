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

- [ ] **Step 1: Write failing service tests**

Cover idempotent start, queued batch creation, cancel, replay-from-failed batches, and deterministic
per-entity request ids.

- [ ] **Step 2: Implement minimal score-all service**

Do not execute heavy scoring in the API request. This slice should produce durable state and deterministic
work items.

- [ ] **Step 3: Run focused service tests**

Expected: service tests pass.

## Task 3: Event And API Surface

**Files:**
- Modify: `backend/events/types.py`
- Modify: `backend/events/codec.py`
- Modify: `backend/api/contracts.py`
- Create or modify: score-run API router/dependencies
- Test: focused event/API tests

- [ ] **Step 1: Add score-run event contract tests**

Events should carry KB id, run id, status, counts, model/catalog versions, and replay lineage.

- [ ] **Step 2: Add start/status/cancel/replay API tests**

Use direct route-function coverage if existing `TestClient` behavior hangs in this environment.

- [ ] **Step 3: Implement routes and event publication**

Keep controls on KB operations/readiness surfaces, not investigator screens.

## Task 4: Frontend Operations Status Slice

**Files:**
- Regenerate OpenAPI/frontend types.
- Add frontend API wrapper and focused KB operations UI test.

- [ ] **Step 1: Add focused UI/API wrapper tests**
- [ ] **Step 2: Implement minimal controls and run status display**
- [ ] **Step 3: Run focused frontend tests and build**

## Task 5: Verification And Closeout

- [ ] Backend focused tests.
- [ ] Frontend focused tests/build if contracts changed.
- [ ] `git diff --check`
- [ ] `python3 scripts/backlog_consistency.py --check`
- [ ] Update backlog and this plan with verification evidence.
