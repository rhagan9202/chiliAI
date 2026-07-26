# Sprint 2026-29 — KB Management Foundations Progress Tracker

Linked plan: [2026-07-26-sprint29-kb-management-foundations.md](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/docs/superpowers/plans/2026-07-26-sprint29-kb-management-foundations.md)

## Team Roster

- Remy (Scrum Master / Producer) — scope control, sequencing, issue linkage
- Sage (Backend Dev) — API contracts, preview endpoint, backend tests
- Nova (Frontend Dev) — KBM 2-step flow, folder upload, preview UX
- Ivy (Tester/QA) — targeted verification, regression checks, sign-off notes

## Phase Status

| Phase | Scope | Owner(s) | Status | Notes |
|---|---|---|---|---|
| 0 | Baseline + failing tests | Remy + Ivy | ✅ Done | Existing targeted suites mapped and passing with updated assertions |
| 1 | KBM-001/002 2-step + single run action | Nova | ✅ Done | Step 1/Step 2 flow implemented with single Run ingestion CTA |
| 2 | KBM-003 folder upload | Nova | ✅ Done | Document folder upload added with relative-path display and tests |
| 3 | KBM-004/005 preview API + panel | Sage + Nova | ✅ Done | Backend preview endpoint shipped; frontend preview panel wired via generated contracts |
| 4 | KBM-006 records preview parity + hardening | Sage + Nova + Ivy | ✅ Done | Records preview parity preserved in unified review step and verified |

## Issue Checklist

| Issue | Title | Status | Evidence |
|---|---|---|---|
| #31 | KBM-001 Re-architect KB Manager into 2-step flow | ✅ Done | [KnowledgeBaseManagerPage.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/KnowledgeBaseManagerPage.tsx), [KnowledgeBaseManagerPage.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx) |
| #32 | KBM-002 Unified ingestion action model | ✅ Done | [SubmitPanel.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/SubmitPanel.tsx), [SubmitPanel.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/__tests__/SubmitPanel.test.tsx) |
| #33 | KBM-003 Folder upload support | ✅ Done | [DocumentSourcePanel.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/DocumentSourcePanel.tsx), [DocumentSourcePanel.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx) |
| #34 | KBM-004 Backend document preview endpoint | ✅ Done | [knowledgebases.py](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/backend/api/routers/knowledgebases.py), [test_knowledgebases_router.py](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/backend/tests/api/test_knowledgebases_router.py) |
| #35 | KBM-005 Frontend document preview panel | ✅ Done | [knowledgebases.ts](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/api/knowledgebases.ts), [KnowledgeBaseManagerPage.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/pages/KnowledgeBaseManagerPage.tsx), [schema.ts](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/lib/api/schema.ts) |
| #36 | KBM-006 Records preview parity | ✅ Done | [RecordsSourcePanel.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/RecordsSourcePanel.tsx), [RecordsSourcePanel.test.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx), [RecordsPreviewTable.tsx](/home/rdhagan92/chiliAI.worktrees/update-kb-management-sprint29-30-plans/chili_app/src/components/ingestion/RecordsPreviewTable.tsx) |

## Communication Log

- 2026-07-26: Sprint tracker initialized. Team execution started with explicit role split (scrum/dev/test/qa) and phased delivery.
- 2026-07-26: Remy sequenced phases and handoff gates. Sage delivered KB preview API and contract tests, then handed to Nova for UI integration.
- 2026-07-26: Nova delivered 2-step flow, unified Run ingestion action, folder upload support, and preview panel integration; handed to Ivy.
- 2026-07-26: Ivy QA completed focused gate sweep (backend + frontend) and signed off all Sprint 29 KBM stories as pass.

## Verification Log

- `cd backend && ../backend/.venv/bin/pytest tests/api/test_knowledgebases_router.py -q` → 41 passed.
- `cd backend && ../backend/.venv/bin/ruff check --no-cache api/routers/knowledgebases.py tests/api/test_knowledgebases_router.py` → all checks passed.
- `cd chili_app && npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx src/components/ingestion/__tests__/SubmitPanel.test.tsx src/components/ingestion/__tests__/RecordsSourcePanel.test.tsx` → 49 passed.
- `cd chili_app && npm run lint` → pass.
- `cd chili_app && npm run build` → pass.
- `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json && cd chili_app && npm run codegen:api` → pass.
- `cd backend && ../backend/.venv/bin/pyright` → 0 errors, 0 warnings after installing missing backend dev deps in the workspace venv.
