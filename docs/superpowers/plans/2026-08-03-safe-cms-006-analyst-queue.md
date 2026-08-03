# SAFE-CMS-006 Analyst Queue And Triage Operations Implementation Plan

**Owner:** Codex
**Date:** 2026-08-03
**Branch:** `fix/normalize-kb-query-param`
**Parent dependencies:** `SAFE-CMS-003`, `SAFE-CMS-005`

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> for implementation slices and `superpowers:test-driven-development` for behavior changes.

## Goal

Upgrade the Alert Feed into a production analyst queue for CMS fraud triage: durable
URL state, high-signal filters, assignment/SLA awareness, evidence preview, bulk
operations, and reviewable suppression/dedup context.

## Current Inventory

- `AlertFeedPage.tsx` already has URL-backed severity/status/search/date/sort filters,
  bulk acknowledge with confirmation, promotion to case, inline evidence viewing, and
  cockpit/Ask AI handoffs.
- `alertFilters.ts` owns the pure frontend filter model and is covered by unit tests.
- `/alerts` currently supports `knowledge_base_id`, one `status`, `limit`, and `offset`
  against the durable alert history store.
- `AlertListItem` exposes severity, status, tags, evidence pack, `created_at`, and
  `updated_at`, but no explicit assignee, SLA due time, case state, score freshness,
  typology, cohort, or suppression/dedup summary fields.
- Case list/detail data can be joined client-side for a first case-state slice because
  cases carry `alert_ids`, `status`, and owner fields.

## Task 1: Queue URL Filters And Operational Metadata

**Files:**
- Modify: `chili_app/src/utils/alertFilters.ts`
- Modify: `chili_app/src/pages/AlertFeedPage.tsx`
- Modify: `chili_app/src/pages/pages.css`
- Test: `chili_app/src/utils/__tests__/alertFilters.test.ts`
- Test: `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx`

- [x] Add URL-backed queue filters for typology/tag, assignee, case state, score freshness,
  and evidence availability.
- [x] Derive assignee and case state from KB-scoped cases for now, without creating a
  conflicting persistence model.
- [x] Surface SLA age buckets from `created_at`/`updated_at` in every row.
- [x] Surface a compact evidence preview in the row, linked to the cockpit/evidence
  state when an evidence pack exists.
- [x] Keep empty-state copy distinct for no data, filtered-away data, and backend error.

Task 1 notes:

- Extended the pure alert filter model with URL-owned `typology`, `assignee`, `case`,
  `freshness`, and `evidence` dimensions while preserving `kb` and selected alert state.
- `AlertFeedPage` now enriches alert rows with case-derived assignee/case state,
  normalized tags, score freshness, evidence availability, and SLA age buckets using
  existing alert/case responses only.
- Rows now show assignee, case state, freshness, SLA state, and a compact evidence
  preview link that opens the existing investigation cockpit with KB, alert, and
  evidence context.
- Empty states now distinguish a truly empty queue from active filters hiding existing
  alerts; backend error state remains the existing `ErrorState`.
- Focused red/green verification:
  - Initial `pnpm exec vitest run src/utils/__tests__/alertFilters.test.ts src/pages/__tests__/AlertFeedPage.test.tsx` failed on six expected missing queue-filter/evidence/empty-state behaviors.
  - After implementation, `pnpm exec vitest run src/utils/__tests__/alertFilters.test.ts src/pages/__tests__/AlertFeedPage.test.tsx`: 56 passed.
- Final verification passed:
  - `pnpm exec vitest run src/utils/__tests__/alertFilters.test.ts src/pages/__tests__/AlertFeedPage.test.tsx`: 56 passed.
  - `pnpm exec eslint src/pages/AlertFeedPage.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/utils/alertFilters.ts src/utils/__tests__/alertFilters.test.ts`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `git diff --check`: passed.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.

## Task 2: Backend Queue Query Contract

**Files:**
- Modify: `backend/api/dependencies.py`
- Modify: `backend/monitoring/adapters/protocols.py`
- Modify: `backend/monitoring/adapters/in_memory.py`
- Modify: `backend/monitoring/adapters/postgres.py`
- Modify: `backend/api/contracts.py`
- Modify/regenerate: `chili_app/src/lib/api/schema.ts`, `chili_app/src/api/alerts.ts`
- Test: `backend/tests/api/test_read_model_routers.py`
- Test: alert store adapter tests
- Test: `chili_app/src/api/__tests__/alerts.test.ts`

- [x] Add queue query parameters for multi-status, severity, typology/tag, date range,
  evidence availability, and score freshness where the store can predicate efficiently.
- [x] Keep pagination totals scoped to the filtered query.
- [x] Preserve existing `status=` behavior for current callers.
- [x] Regenerate the OpenAPI/frontend contract after backend schema changes.

Task 2 notes:

- Extended `AlertFeedStoreProtocol`, in-memory alert history, and Postgres alert history
  with store-backed filters for repeated `status`, repeated `severity`, repeated
  `typology`/tag, inclusive `from`/`to` created-date bounds, evidence availability, and
  14-day score freshness from `updated_at`.
- `get_alert_list_payload` now passes those API query params directly into the store, so
  filtered totals remain owned by the persistence layer.
- `getAlerts` serializes the same queue params and `AlertFeedPage` sends store-backed
  filters to `/alerts`; assignee and case-state filtering remain client-derived until
  Task 3 adds durable assignment/status operations.
- Regenerated `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts`.
- Focused red/green verification:
  - Initial store test failed with `unexpected keyword argument 'severities'`.
  - Initial frontend API test failed because `getAlerts` omitted the new query params.
  - After implementation, backend store/API dependency tests and frontend API/page/filter
    tests passed.
- Final verification passed:
  - `backend/.venv/bin/python -m pytest backend/tests/api/test_read_model_routers.py::test_list_alerts_route_passes_queue_filters_to_store backend/tests/monitoring/test_alert_store_kb_scope.py`: passed when run outside the command sandbox.
  - `backend/.venv/bin/ruff check backend/api/dependencies.py backend/monitoring/adapters/protocols.py backend/monitoring/adapters/in_memory.py backend/monitoring/adapters/postgres.py backend/tests/api/test_read_model_routers.py backend/tests/monitoring/test_alert_store_kb_scope.py`: passed.
  - `backend/.venv/bin/pyright --project backend backend/api/dependencies.py backend/monitoring/adapters/protocols.py backend/monitoring/adapters/in_memory.py backend/monitoring/adapters/postgres.py`: 0 errors.
  - `pnpm exec vitest run src/api/__tests__/alerts.test.ts src/pages/__tests__/AlertFeedPage.test.tsx src/utils/__tests__/alertFilters.test.ts`: 57 passed.
  - `pnpm exec eslint src/api/alerts.ts src/api/__tests__/alerts.test.ts src/pages/AlertFeedPage.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/utils/alertFilters.ts src/utils/__tests__/alertFilters.test.ts`: passed.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `git diff --check`: passed.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.
- Root-cause follow-up (2026-08-03): sandboxed route tests were timing out because
  Starlette `TestClient` depends on AnyIO/asyncio cross-thread event-loop wakeups; a
  minimal plain FastAPI `TestClient` and direct `loop.call_soon_threadsafe` reproduction
  both hung in the sandbox, while the same plain `TestClient` passed outside it. The
  `SAFE-CMS-006` queue route test remains route-level coverage and must be run with
  sandbox escalation in this environment, not replaced with a direct dependency call.

## Task 3: Assignment And Status Operations

**Files:**
- Modify: alert history model/store/router and frontend mutations.
- Test: backend route/store tests and alert feed mutation tests.

- [x] Add auditable single-alert assignment and status transition operations.
- [x] Add confirmed bulk status changes beyond acknowledge only where transitions are valid.
- [x] Show assignee and aging/SLA risk in the queue for supervisors.
- [x] Invalidate the same alert query families used by realtime updates.

Task 3 notes:

- Added durable alert assignment and triage audit fields to `AlertHistoryRecord`,
  the Postgres migration chain, and the clean-install schema snapshot.
- Centralized alert lifecycle validation in `monitoring.lifecycle` so the existing
  monitoring service and new alert-history mutations share one transition table.
- Added KB-scoped store operations for assignment and status transitions. In-memory
  and Postgres adapters update by `(knowledge_base_id, alert_id)` for new mutation
  paths, append typed audit events with server-derived actors, and reject invalid
  lifecycle transitions without writing partial single-alert changes.
- Added `PATCH /alerts/{id}/assignment`, `PATCH /alerts/{id}/status`, and
  `POST /alerts/bulk/status`, with route coverage for audit receipts, missing KB
  validation, wrong-KB refusal, invalid-transition `409`, and bulk skipped-row
  reporting.
- Added frontend alert mutations and hooks for assignment, single status, and bulk
  status updates. Each invalidates `alertsQueryKey`, matching realtime and
  acknowledge cache refresh behavior.
- `AlertFeedPage` now prefers durable alert-level assignee over case-derived fallback,
  shows row assignment controls, gates single-row status options to valid next
  transitions, and confirms bulk status updates grouped by alert KB.
- Focused red/green verification:
  - Initial store tests failed on missing `assign` and `transition_status` methods.
  - Initial route tests failed with `404` for missing assignment/status/bulk routes.
  - Initial frontend API/page tests failed on missing mutation functions, hooks, and
    row/bulk controls.
  - After implementation, focused backend store/API/Postgres and frontend API/page
    tests passed.
- Verification passed:
  - `backend/.venv/bin/python -m pytest backend/tests/monitoring/test_alert_history_writer.py backend/tests/monitoring/test_service.py::test_transition_allows_valid_transitions backend/tests/monitoring/test_service.py::test_transition_to_resolved_records_actor_and_notes -q`: 29 passed.
  - `backend/.venv/bin/python -m pytest backend/tests/monitoring/test_postgres_alert_history.py -q`: 7 passed against local Docker Postgres after `docker compose -f docker-compose.dev.yaml up -d --wait postgres` and Alembic upgrade.
  - `backend/.venv/bin/python -m pytest backend/tests/api/test_read_model_routers.py::test_assign_alert_route_returns_updated_alert_and_audit_event backend/tests/api/test_read_model_routers.py::test_update_alert_status_route_enforces_valid_transitions backend/tests/api/test_read_model_routers.py::test_update_alert_status_route_returns_updated_alert_and_audit_event backend/tests/api/test_read_model_routers.py::test_alert_triage_mutations_require_knowledge_base_scope backend/tests/api/test_read_model_routers.py::test_alert_triage_mutations_refuse_an_alert_from_another_knowledge_base backend/tests/api/test_read_model_routers.py::test_bulk_alert_status_route_updates_only_valid_scoped_transitions -q`: 6 passed outside the command sandbox.
  - `backend/.venv/bin/ruff check ...`: passed on touched backend files.
  - `backend/.venv/bin/pyright --project backend ...`: 0 errors.
  - `pnpm exec vitest run src/api/__tests__/alerts.test.ts src/pages/__tests__/AlertFeedPage.test.tsx src/utils/__tests__/alertFilters.test.ts`: 65 passed.
  - `pnpm exec eslint ...`: passed on touched frontend files.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api` from `chili_app/`: passed.
  - `scripts/ci_migration_check.sh`: passed outside the command sandbox; migration replay clean and schema matched `backend/database/migrations/snapshots/head.sql`.
  - `pnpm build`: passed with the existing Vite large-chunk warning.

## Task 4: Suppression, Dedup, And Final Browser Flow

**Files:**
- Modify: monitoring alert generation/store payload shape as needed.
- Modify: `AlertFeedPage.tsx` and focused e2e tests.
- Test: monitoring service tests, alert feed tests, and Playwright triage flow.

- [ ] Preserve suppression/dedup reason metadata from alert generation into the queue.
- [ ] Show reviewer-readable suppression/dedup decisions without crowding the row.
- [ ] Add keyboard navigation and browser flow coverage for filtering, previewing evidence,
  bulk action confirmation, and cockpit handoff.
- [ ] Run focused frontend/backend checks, build, `git diff --check`, and backlog
  consistency before completion.

## Definition Of Done

- Queue supports saved URL state for all Sprint 6 filters and selected alert/evidence.
- Analysts can scan findings, SLA age, case state, assignee, and evidence preview without
  leaving the queue.
- Supervisors can assign and transition work with audit receipts.
- Reviewers can understand visible suppression/dedup decisions.
- API/store filters are covered, frontend route-state tests are covered, keyboard/browser
  verification is recorded, and no unrelated regressions are introduced.
