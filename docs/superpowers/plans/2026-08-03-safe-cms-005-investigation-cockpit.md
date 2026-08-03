# SAFE-CMS-005 Unified Fraud Investigation Cockpit Implementation Plan

**Owner:** Codex
**Date:** 2026-08-03
**Branch:** `fix/normalize-kb-query-param`
**Parent dependencies:** `SAFE-CMS-003`, `SAFE-CMS-004`

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> for implementation slices and `superpowers:test-driven-development` for behavior changes.

## Goal

Turn the existing investigation workbench into a shareable fraud cockpit where an analyst
or supervisor can open one URL and recover the knowledge base, entity, alert, case,
evidence pack, graph context, risk signals, policy signals, and AI handoff context.

## Current Inventory

- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` already supports
  `/investigation/:entityId?kb=...`, KB selection, entity search, risk/timeseries,
  graph neighborhood, policy, and evidence tabs.
- Evidence in the workbench is inferred from the first KB-scoped alert matching the
  selected entity. It does not yet honor `?alert=`, `?case=`, or `?evidence=`.
- `AlertFeedPage.tsx` links rows to `/investigation/:entityId?kb=...` and can render
  alert evidence inline, but it does not deep-link the cockpit with the selected alert
  and evidence pack.
- `cases.ts` exposes `useCase(knowledgeBaseId, caseId)` and case detail can carry
  alerts and an evidence pack, so the first cockpit slice can compose existing APIs.
- The route table already has both `/investigation` and `/investigation/:entityId`.

## Task 1: Cockpit URL State And Alert Deep Links

**Files:**
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Modify: `chili_app/src/pages/AlertFeedPage.tsx`
- Test: `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`
- Test: `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx`

- [x] **Step 1: Write failing route-state tests**

Cover `/investigation/:entityId?kb=...&alert=...&case=...&evidence=...` selecting the
explicit alert/evidence context, rendering useful cockpit state labels, and launching
Ask AI with the same explicit context.

- [x] **Step 2: Parse cockpit state from URL**

Centralize query parsing for `kb`, `alert`, `case`, `evidence`, and `depth`. Prefer the
URL-selected alert when it belongs to the selected entity and active KB; otherwise fall
back to the current entity-matching alert behavior. Prefer the URL-selected evidence pack
when present.

- [x] **Step 3: Surface first-viewport cockpit context**

Add a compact operational context rail showing selected knowledge base, entity, alert,
case, evidence pack, and empty/unknown states without blocking the existing tabs.

- [x] **Step 4: Preserve state during navigation and AI handoff**

Entity search, graph-node selection, Alert Feed investigate links, and Ask AI launches
must preserve `kb`, valid `alert`, `case`, and `evidence` context where appropriate.

- [x] **Step 5: Focused verification**

Run the workbench and alert feed tests, focused ESLint on touched frontend files,
`pnpm build`, `git diff --check`, and `backend/.venv/bin/python scripts/backlog_consistency.py --check`.

Task 1 notes:

- Added explicit cockpit URL parsing for `alert`, `case`, and `evidence` alongside the
  existing `kb` and `depth` handling.
- The workbench now prefers a URL-selected alert only when it belongs to the selected
  entity and active knowledge base; otherwise it keeps the previous entity-alert fallback.
- Added a compact cockpit state card showing KB, entity, alert, case, and evidence context
  with loading/error states for optional case and evidence details.
- Alert Feed investigate links now enter `/investigation/:entityId` with `kb`, `alert`,
  and `evidence` query parameters when evidence exists.
- Review hardening: invalid explicit alerts no longer silently fall back to a different
  entity alert; invalid cases/evidence are displayed as unavailable and dropped from
  Ask AI handoff; switching knowledge bases clears stale `alert`, `case`, and `evidence`
  parameters.
- Focused red/green verification:
  - `pnpm exec vitest run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx`: 59 passed.
- Final verification passed:
  - `pnpm exec vitest run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx`: 63 passed.
  - `pnpm exec eslint src/pages/InvestigationWorkbenchPage.tsx src/pages/AlertFeedPage.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `git diff --check`: passed.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.

## Task 2: Dense Cockpit Shell And Action Rail

**Files:**
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Modify: `chili_app/src/pages/pages.css`
- Create/modify: cockpit-presentational components only if duplication becomes real
- Test: workbench component tests

- [ ] Promote the first viewport from tab-first investigation to a cockpit shell:
  entity dossier, risk summary, current alert/case/evidence state, graph/evidence region,
  RAG launch, and case actions.
- [ ] Keep layout dense and operational across desktop, tablet, and mobile.
- [ ] Include empty states for missing graph, evidence, policy, peer context, and case.

Task 2 notes:

- First action-rail slice added validated first-viewport actions for the active cockpit
  context: open selected alert, open selected case, and jump to the selected evidence pack.
- The actions receive only validated alert/case/evidence IDs from Task 1, so invalid URL
  context remains visible as unavailable but is not offered as an operational handoff.
- Added a compact first-viewport cockpit overview for risk, graph neighborhood size,
  case state, and selected evidence pack, all composed from existing workbench queries.
- Focused red/green verification:
  - `pnpm exec vitest run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: 32 passed.
  - `pnpm exec vitest run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: 33 passed.
- Final verification passed:
  - `pnpm exec vitest run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx`: 65 passed.
  - `pnpm exec eslint src/pages/InvestigationWorkbenchPage.tsx src/pages/AlertFeedPage.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `git diff --check`: passed.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.

## Task 3: Peer, Typology, And Policy Context Panels

**Files:**
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Reuse: `FeatureList`, `SignalBand`, policy panel, GNN/cluster panels
- Test: workbench component tests

- [ ] Make typologies and feature values visible as cockpit context, not only tab detail.
- [ ] Surface peer-context availability with domain-neutral labels.
- [ ] Keep non-CMS domains using `DomainConfig` labels and empty states.

## Task 4: Alert-To-Case Cockpit Continuity

**Files:**
- Modify: `AlertFeedPage`, `CaseManagementPage`, and RAG/citation navigation only where
  links enter the cockpit.
- Test: Alert Feed, Case Management, RAG navigation tests

- [ ] Preserve cockpit context when an alert is promoted or attached to a case.
- [ ] Add supervisor-friendly deep links from case and RAG contexts back to the same
  investigation state.

## Task 5: Responsive And Browser Verification

**Files:**
- Modify: frontend CSS and E2E coverage as needed
- Test: Playwright or browser smoke where stack startup permits

- [ ] Verify graph/evidence space does not fight on desktop/tablet/mobile.
- [ ] Confirm no text overlaps and all primary actions remain reachable.
- [ ] Capture screenshots or Playwright evidence for the final checkpoint.

## Definition Of Done

- CMS alert opens directly into the cockpit with correct KB/entity/alert/evidence context.
- Cockpit supports `kb`, `alert`, `case`, `evidence`, and selected entity deep links.
- Missing graph/evidence/policy/case states are useful and domain-neutral.
- Domain labels come from config; no CMS-only labels are hardcoded into reusable UI.
- Focused tests, build, whitespace check, and backlog consistency pass, with known
  unrelated failures called out explicitly.
