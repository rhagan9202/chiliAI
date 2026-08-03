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

- [ ] Add queue query parameters for multi-status, severity, typology/tag, date range,
  evidence availability, and score freshness where the store can predicate efficiently.
- [ ] Keep pagination totals scoped to the filtered query.
- [ ] Preserve existing `status=` behavior for current callers.
- [ ] Regenerate the OpenAPI/frontend contract after backend schema changes.

## Task 3: Assignment And Status Operations

**Files:**
- Modify: alert history model/store/router and frontend mutations.
- Test: backend route/store tests and alert feed mutation tests.

- [ ] Add auditable single-alert assignment and status transition operations.
- [ ] Add confirmed bulk status changes beyond acknowledge only where transitions are valid.
- [ ] Show assignee and aging/SLA risk in the queue for supervisors.
- [ ] Invalidate the same alert query families used by realtime updates.

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
