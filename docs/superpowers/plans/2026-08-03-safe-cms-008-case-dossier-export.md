# SAFE-CMS-008 Case Dossier And Export Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cases the durable investigation record by exposing a dossier read model and export workflow that preserve alerts, evidence, chronology, decisions, notes, and citation provenance.

**Architecture:** Extend the existing KB-scoped case service/API instead of storing dossier state in the frontend. Dossier responses aggregate the durable `Case`, linked alert rows, case timeline, analyst feedback, and referenced evidence packs. Export is a projection of the dossier read model; it must not bypass KB scoping or include unsupported raw secrets.

**Tech Stack:** FastAPI, Pydantic contracts, existing case repositories, alert history store, evidence pack repository, React Query, React, Vitest, Playwright, OpenAPI codegen.

---

## Current Inventory

- `backend/cases/models.py` already stores durable case status, priority, assignee, originating alert, evidence pack id, linked alert ids, timeline, and feedback history.
- `backend/api/routers/cases.py` exposes list/detail/create/promote/attach/update/feedback, but no dossier or case export endpoint.
- `backend/api/dependencies.py` assembles `CaseDetailResponse` with linked alerts and one originating evidence pack.
- `chili_app/src/pages/CaseManagementPage.tsx` renders case queue/detail, timeline, feedback, cockpit links, and Ask AI launch, but not a formal dossier/export view.
- `EvidencePackActions` already exports one evidence pack; SAFE-CMS-008 needs case-level export that can include multiple evidence packs and feedback history.

## Task 1: Backend Dossier Read Model And Export

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/routers/cases.py`
- Test: `backend/tests/api/test_phase5_stateful_routes.py`
- Modify: `docs/superpowers/plans/2026-08-03-safe-cms-008-case-dossier-export.md`

- [x] **Step 1: Write failing API tests**

Add tests proving:

- `GET /cases/{case_id}/dossier?knowledge_base_id=...` returns case summary, linked alerts, timeline, feedback history, all KB-scoped referenced evidence packs, and export metadata.
- Dossier evidence packs are deduplicated across `case.evidence_pack_id` and linked alert `evidence_pack_id` values.
- Wrong-KB dossier lookup returns `404`.
- `GET /cases/{case_id}/dossier/export?knowledge_base_id=...&format=markdown` includes case title, status, linked alerts, timeline, feedback, evidence reasoning, and provenance labels.
- JSON export returns machine-readable dossier content and a `.json` filename.

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json -q
```

Expected: fail because the dossier routes and contracts do not exist.

- [x] **Step 3: Implement minimal dossier contracts and routes**

Add `CaseDossierEvidenceResponse`, `CaseDossierExportMetadataResponse`, `CaseDossierResponse`, and `CaseDossierExportResponse`. Add dependency builders that reuse the existing case, alert, and evidence repositories. Build evidence pack ids from the case origin and linked alerts, dedupe while preserving order, and enforce the existing KB-scoped case lookup before export.

- [x] **Step 4: Run tests to verify GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json -q
```

Expected: the new dossier route tests pass.

- [x] **Step 5: Commit Task 1**

Run focused formatting/checks and commit only Task 1 files.

Task 1 notes:

- Added `CaseDossierResponse` and `CaseDossierExportResponse` contracts.
- Added KB-scoped `GET /cases/{case_id}/dossier` and
  `GET /cases/{case_id}/dossier/export` routes.
- Dossier evidence packs are collected from the case origin and linked alerts,
  deduped in stable order, and loaded through the KB-scoped evidence repository.
- Markdown export includes case status/priority, linked alerts, timeline,
  evidence reasoning, provenance labels, and analyst feedback. JSON export is
  the machine-readable dossier payload.
- Red verification failed as expected with `404` on the missing dossier routes:
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json -q`
- Green verification passed:
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json -q`: 2 passed.
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py -q`: 12 passed.
  - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/routers/cases.py backend/tests/api/test_phase5_stateful_routes.py`: passed.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api`: passed.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.
  - `git diff --check`: passed.

## Task 2: Frontend Dossier API And Case Page Export Controls

**Files:**
- Modify: `chili_app/src/api/cases.ts`
- Modify generated contracts after OpenAPI export/codegen.
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Test: `chili_app/src/pages/__tests__/CaseManagementPage.test.tsx`
- Modify: `docs/superpowers/plans/2026-08-03-safe-cms-008-case-dossier-export.md`

- [x] Add React Query hooks for case dossier and export.
- [x] Render a dossier section that separates chronology, evidence bundle, decisions, and export actions.
- [x] Keep the existing compact case detail usable while making export a clear case-level action.
- [x] Verify with focused Vitest, ESLint, build, OpenAPI/codegen, and backlog consistency.

Task 2 notes:

- Added typed frontend aliases for `CaseDossierResponse` and
  `CaseDossierExportResponse`.
- Added `caseDossierQueryKey`, `getCaseDossier`, `exportCaseDossier`, and
  `useCaseDossier` in `chili_app/src/api/cases.ts`.
- Case mutations that can affect dossier content now invalidate the dossier
  query alongside the case list/detail queries.
- `CaseManagementPage` now renders a route-backed Case dossier region with
  evidence bundle, chronology, decisions, and case-level Markdown/JSON export
  controls that use the existing browser download utility.
- Red verification failed on missing dossier API helpers, missing
  `useCaseDossier` usage, and missing export buttons:
  - `pnpm exec vitest run src/api/__tests__/cases.test.ts src/pages/__tests__/CaseManagementPage.test.tsx`
- Green verification passed:
  - `pnpm exec vitest run src/api/__tests__/cases.test.ts src/pages/__tests__/CaseManagementPage.test.tsx`: 22 passed.
  - `pnpm exec vitest run src/api/__tests__/cases.test.ts src/pages/__tests__/CaseManagementPage.test.tsx src/components/investigation/__tests__/EvidencePackActions.test.tsx`: 30 passed.
  - `pnpm exec eslint src/api/cases.ts src/api/contracts.ts src/api/__tests__/cases.test.ts src/pages/CaseManagementPage.tsx src/pages/__tests__/CaseManagementPage.test.tsx`: passed.
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json -q`: 2 passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.
  - `git diff --check`: passed.
- Review note: two review subagents were spawned for Task 2, but this tool
  surface only exposed spawn/close and both were shut down before returning
  findings. Local review caught and fixed stale dossier invalidation before
  final verification.

## Task 3: Browser Alert-To-Case-To-Dossier Flow

**Files:**
- Create/modify: `chili_app/e2e/case-dossier.spec.ts`
- Modify: `docs/superpowers/plans/2026-08-03-safe-cms-008-case-dossier-export.md`

- [x] Seed the real dev stack, promote an alert, open the selected case dossier, export it, and verify cited evidence/provenance is present.
- [x] Run focused Playwright and full story checks.

**Notes:**
- Added `chili_app/e2e/case-dossier.spec.ts` for the seeded alert-to-case-to-dossier browser flow.
- RED: focused Playwright exposed that Markdown exports preserved provenance labels/types but omitted source identifiers (`dev-seed-source`).
- Fixed `_render_case_dossier_markdown` through a bounded provenance formatter that includes `reference_id`, route target, source/version, and transform version.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json -q`: passed.
  - `pnpm exec playwright test e2e/case-dossier.spec.ts`: passed against the rebuilt dev stack.
  - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_evidence_feedback_and_export_metadata backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_export_renders_markdown_and_json -q`: passed.
  - `pnpm exec vitest run src/api/__tests__/cases.test.ts src/pages/__tests__/CaseManagementPage.test.tsx`: 22 passed.
  - `pnpm exec eslint src/api/cases.ts src/api/contracts.ts src/api/__tests__/cases.test.ts src/pages/CaseManagementPage.tsx src/pages/__tests__/CaseManagementPage.test.tsx e2e/case-dossier.spec.ts`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.
  - `git diff --check`: passed.
- Final local review found no blocking issues. Backlog status remains unchanged pending the next explicit closeout decision because evidence removal/reason-code chronology is documented as a DoD residual/follow-up item.

## Deferred Follow-Up

- `SAFE-CMS-008-FU-001`: add explicit analyst-driven evidence add/remove actions with reason codes and case chronology entries. Current SAFE-CMS-008 implementation preserves originating and attached-alert evidence chronology; explicit evidence removal remains out of this surge slice.

## Review Gates

- Review after backend dossier contracts before frontend codegen/UI.
- Review after frontend unit coverage before browser flow.
- Final review before backlog status changes and push.

## Definition Of Done

- Case dossier opens from route-backed KB/case context.
- Promotion preserves originating alert and evidence context.
- Evidence additions/removals are represented with reasoned chronology, or remain explicitly deferred with a tracked follow-up.
- Export includes citations/provenance, timeline, feedback, and linked alerts.
- Wrong-KB case, alert, and evidence references do not leak across scopes.
- Focused backend tests, frontend tests, lint, build, browser flow, backlog consistency, and whitespace checks pass.
