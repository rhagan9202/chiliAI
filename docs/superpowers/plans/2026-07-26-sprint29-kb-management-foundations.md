# Sprint 2026-29 — Knowledge Base Manager Foundations (KBM-001..006) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the Sprint 1 KB Manager foundations: a clear 2-step ingestion flow with one primary ingestion CTA, folder upload support, and preview parity across documents and records so analysts can review before running ingestion.

**Architecture:** Keep orchestration in FastAPI + existing workflow services; keep KB Manager UX in [KnowledgeBaseManagerPage.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/KnowledgeBaseManagerPage.tsx) with API DTOs sourced from generated contracts only.

**Tech Stack:** FastAPI/Pydantic, React 19 + TypeScript, TanStack Query, Vitest, pytest.

**Open issue source (pushed 2026-07-26):**
- [#31 KBM-001](https://github.com/rhagan9202/chiliAI/issues/31) — Re-architect KB Manager into 2-step flow
- [#32 KBM-002](https://github.com/rhagan9202/chiliAI/issues/32) — Unified ingestion action model
- [#33 KBM-003](https://github.com/rhagan9202/chiliAI/issues/33) — Folder upload support
- [#34 KBM-004](https://github.com/rhagan9202/chiliAI/issues/34) — Backend document preview endpoint
- [#35 KBM-005](https://github.com/rhagan9202/chiliAI/issues/35) — Frontend document preview panel
- [#36 KBM-006](https://github.com/rhagan9202/chiliAI/issues/36) — Records preview parity

---

## Execution Phases (Sprint 29)

### Phase 0 — Contract/test prep (KBM-001..006 baseline)

- [ ] Confirm issue acceptance criteria in [#31](https://github.com/rhagan9202/chiliAI/issues/31)-[#36](https://github.com/rhagan9202/chiliAI/issues/36) and map each to at least one test assertion.
- [ ] Run current targeted suites once to establish baseline:
  - `cd chili_app && npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx`
  - `cd backend && ../backend/.venv/bin/pytest tests/api/test_knowledgebases_router.py -q`
- [ ] Add failing tests for each new behavior before implementation changes.

### Phase 1 — UX flow foundation (KBM-001 + KBM-002)

- [ ] Implement 2-step KBM flow and single “Run ingestion” CTA in page + ingestion components.
- [ ] Keep existing KB selection and handoff behavior stable.
- [ ] Pass focused frontend tests before moving on.

### Phase 2 — Source staging expansion (KBM-003)

- [ ] Add folder upload support and validation paths in document source panel/store.
- [ ] Preserve existing single-file behavior and receipt semantics.
- [ ] Pass panel/store tests and targeted page tests.

### Phase 3 — Preview APIs + UI (KBM-004 + KBM-005)

- [ ] Add backend document preview contract/route and tests.
- [ ] Regenerate OpenAPI + frontend contracts.
- [ ] Add frontend preview panel wiring with loading/error/empty states.
- [ ] Pass backend router tests and frontend preview tests.

### Phase 4 — Records preview parity + integration hardening (KBM-006)

- [ ] Extend unified review flow to records preview parity.
- [ ] Reuse shared preview presentation pattern across document/records paths.
- [ ] Run full touched-area suites and quality gates.
- [ ] Prepare PR with issue-linked commits and verification notes.

---

## Implementation Checklist By File

### Frontend page and orchestration

- [ ] [chili_app/src/pages/KnowledgeBaseManagerPage.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/KnowledgeBaseManagerPage.tsx)
  - [ ] Introduce/solidify 2-step flow structure.
  - [ ] Enforce one canonical “Run ingestion” action.
  - [ ] Wire preview selection state (document and records).
  - [ ] Keep active KB context and downstream handoff links intact.

- [ ] [chili_app/src/stores/ingestionStudioStore.ts](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/stores/ingestionStudioStore.ts)
  - [ ] Add/adjust state needed for unified review + preview parity.
  - [ ] Preserve existing run/workflow tracking semantics.

### Frontend ingestion components

- [ ] [chili_app/src/components/ingestion/DocumentSourcePanel.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/DocumentSourcePanel.tsx)
  - [ ] Add folder upload input behavior.
  - [ ] Keep file filtering + validation messaging consistent.

- [ ] [chili_app/src/components/ingestion/RecordsSourcePanel.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/RecordsSourcePanel.tsx)
  - [ ] Align records source UX with unified 2-step review model.

- [ ] [chili_app/src/components/ingestion/SubmitPanel.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/SubmitPanel.tsx)
  - [ ] Ensure only one user-facing submit/run pathway remains.

- [ ] [chili_app/src/components/ingestion/RecordsPreviewTable.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/RecordsPreviewTable.tsx)
  - [ ] Implement review parity expectations relative to document preview.

- [ ] [chili_app/src/components/ingestion/ingestion.css](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/ingestion.css) and/or [chili_app/src/pages/pages.css](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/pages.css)
  - [ ] Add minimal layout/styles needed for step flow + preview panel states.

### Frontend API contracts

- [ ] [chili_app/src/lib/api/schema.ts](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/lib/api/schema.ts) (generated)
  - [ ] Regenerate after backend preview model changes (`npm run codegen:api`).

- [ ] [chili_app/src/api/contracts.ts](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/api/contracts.ts)
  - [ ] Verify aliases expose new/updated preview DTOs.

### Backend API and service surface

- [ ] [backend/api/routers/knowledgebases.py](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/backend/api/routers/knowledgebases.py)
  - [ ] Add/adjust document preview route (bounded response for first N lines/chars).
  - [ ] Keep response typed via Pydantic models and explicit errors.

- [ ] [backend/api/contracts.py](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/backend/api/contracts.py)
  - [ ] Add/adjust request/response models used by preview route.

- [ ] backend ingestion/records service module(s) selected during implementation
  - [ ] Add preview payload construction logic with explicit limits.
  - [ ] Avoid cross-module coupling outside approved boundaries.

### Tests

- [ ] [chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx)
  - [ ] Step gating + single-run CTA coverage.
  - [ ] Document/records preview flow assertions.

- [ ] [chili_app/src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx)
  - [ ] Folder upload, nested file handling, unsupported file behavior.

- [ ] [chili_app/src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx)
  - [ ] Records source + review parity expectations.

- [ ] [chili_app/src/components/ingestion/__tests__/SubmitPanel.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/__tests__/SubmitPanel.test.tsx)
  - [ ] Single-action ingestion assertions.

- [ ] [backend/tests/api/test_knowledgebases_router.py](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/backend/tests/api/test_knowledgebases_router.py)
  - [ ] Preview route contract/error-path tests.

- [ ] Add/adjust backend ingestion/records unit tests adjacent to touched service modules.

## Task 1 — KBM-001 + KBM-002: Two-step flow + single “Run ingestion” action

- [ ] Convert KB Manager into explicit Step 1 (stage sources) and Step 2 (review + run ingestion) flow.
- [ ] Replace fragmented submit actions with one canonical “Run ingestion” CTA mapped to existing backend workflow start.
- [ ] Preserve existing query/selection behavior for active KB id and route handoffs.
- [ ] Add/adjust tests that fail first for step gating and single-action behavior.
- [ ] Validate frontend gates for touched files.

## Task 2 — KBM-003: Folder upload support for policy docs

- [ ] Add folder upload capability in the document staging UX (`webkitdirectory` flow or existing repo-approved pattern).
- [ ] Ensure accepted-file filtering and receipt model remain aligned with backend document ingestion constraints.
- [ ] Add tests for mixed nested folders, unsupported files, and receipt counts.
- [ ] Verify no regression in single-file document uploads.

## Task 3 — KBM-004 + KBM-005: Document preview endpoint + inventory preview panel

- [ ] Add backend preview route for first N lines/chars with explicit size limits and typed response models.
- [ ] Wire frontend preview panel in KB inventory to call generated API client contracts (no handwritten wire DTOs).
- [ ] Add loading/error/empty states consistent with existing page patterns.
- [ ] Cover with API tests and component tests.

## Task 4 — KBM-006: Records preview parity in unified review flow

- [ ] Extend Step 2 review to provide records preview parity with document preview expectations.
- [ ] Reuse shared preview presentation model where possible; avoid duplicate rendering logic.
- [ ] Add tests proving both document and records paths are reviewable before Run ingestion.
- [ ] Confirm handoff copy and run-state UX remain coherent.

## Success Criteria

- [ ] Issues [#31](https://github.com/rhagan9202/chiliAI/issues/31) through [#36](https://github.com/rhagan9202/chiliAI/issues/36) are implemented and linked by commits/PR.
- [ ] KB Manager has one primary ingestion action and clear step progression.
- [ ] Folder uploads, document preview, and records preview all work from the same review flow.
- [ ] Frontend: `npm run lint`, `npm run test:run`, `npm run build` pass.
- [ ] Backend: `pytest --cov`, `pyright`, `ruff check --no-cache .` pass for touched areas.

## Out of Scope for Sprint 29

- Delete modes and destructive cleanup semantics (Sprint 30 issues [#37](https://github.com/rhagan9202/chiliAI/issues/37)-[#39](https://github.com/rhagan9202/chiliAI/issues/39))
- Rebuild controls/timeline orchestration ([#41](https://github.com/rhagan9202/chiliAI/issues/41), [#42](https://github.com/rhagan9202/chiliAI/issues/42))
- Telemetry/runbook follow-through ([#43](https://github.com/rhagan9202/chiliAI/issues/43), [#44](https://github.com/rhagan9202/chiliAI/issues/44))
