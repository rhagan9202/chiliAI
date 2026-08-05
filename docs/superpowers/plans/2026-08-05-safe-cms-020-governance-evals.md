# SAFE-CMS-020 Governance And Evaluation Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first SAFE-CMS-020 governance surface: a KB-scoped release-readiness report that inventories published playbook versions, approved workflow definitions, pending approvals, challenged explanations, and release blockers.

**Architecture:** Build a new backend `governance` module that composes existing playbook, workflow-definition, and explanation-review repositories without introducing a new persistence store in this slice. Expose a viewer-gated `GET /knowledgebases/{knowledge_base_id}/governance/report` route, regenerate frontend contracts, then add a compact supervisor dashboard route driven by the active knowledge base.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pytest, pyright, React 19, TypeScript, Vite 8, TanStack Query, Vitest, Playwright.

---

## File Structure

- Create `backend/governance/models.py`: report DTOs for version inventory, feedback trends, pending approvals, and release blockers.
- Create `backend/governance/service.py`: pure report builder over existing repositories/services.
- Create `backend/governance/__init__.py`: public module exports.
- Create `backend/tests/governance/test_service.py`: TDD coverage for report semantics.
- Modify `backend/api/contracts.py`: frontend-facing governance response models.
- Create `backend/api/routers/governance.py`: KB-scoped governance report route.
- Modify `backend/api/app.py`: include the governance router.
- Modify `backend/api/dependencies.py`: provide `GovernanceReportService`.
- Create `backend/tests/api/test_governance_router.py`: route auth, KB scoping, and response tests.
- Regenerate `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts`.
- Create `chili_app/src/api/governance.ts`: query helper and hook.
- Create `chili_app/src/api/__tests__/governance.test.ts`: API serialization tests.
- Create `chili_app/src/pages/GovernancePage.tsx`: compact governance dashboard.
- Modify `chili_app/src/app/router.tsx`: add `/governance`.
- Modify `chili_app/src/app/access.ts`: map `/governance` to `governance`.
- Modify `chili_app/src/components/layout/Sidebar.tsx`: add governance icon fallback.
- Modify `chili_app/src/pages/__tests__/GovernancePage.test.tsx`: page states and report rendering.
- Modify `backend/config/defaults/medicare_fraud.yaml` and `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`: add supervisor-visible Governance page.
- Modify `backend/tests/config/test_schema.py`: assert CMS packs expose governance only to supervisor.
- Modify `backend/README.md`, `chili_app/README.md`, `docs/architecture.md`, and this plan with final status and usage notes.

## Implementation Status

- Completed in this pass: Tasks 1 through 5 implementation, Task 6 final verification, focused review fixes, frontend governance dashboard wiring, config/docs wiring, and live-stack e2e smoke.
- Remaining work: finish branch into `prod` only.

---

### Task 1: Backend Governance Report Service

**Files:**
- Create: `backend/governance/models.py`
- Create: `backend/governance/service.py`
- Create: `backend/governance/__init__.py`
- Test: `backend/tests/governance/test_service.py`

- [x] **Step 1: Write failing service tests**

Create tests that build in-memory playbook, workflow-definition, and explanation-review stores and assert:

- Published playbook snapshots appear as production versions.
- Approved workflow definitions appear as production versions.
- Draft workflow definitions appear in pending approvals and release blockers.
- Challenged explanation reviews are counted in feedback trends and create a warning blocker.
- A KB with no published playbooks creates a blocking release blocker.

- [x] **Step 2: Run focused RED**

Run:

```bash
uv run --project backend pytest backend/tests/governance/test_service.py -q
```

Expected: FAIL because `governance.service` and `governance.models` do not exist.

Result:

- `uv run --project backend pytest backend/tests/governance/test_service.py -q`: failed during collection with `ModuleNotFoundError: No module named 'governance'`.

- [x] **Step 3: Implement minimal report models and service**

Implement:

- `GovernanceVersionSummary`: `component_kind`, `component_id`, `version`, `status`, `source`, `approved_by`, `approved_at`.
- `GovernancePendingApproval`: `approval_kind`, `resource_id`, `version`, `status`, `requested_by`, `updated_at`.
- `GovernanceFeedbackTrend`: `total_reviews`, `challenged_reviews`, `approved_reviews`, `state_counts`.
- `GovernanceReleaseBlocker`: `severity`, `code`, `message`, `resource_type`, `resource_id`.
- `GovernanceReport`: `knowledge_base_id`, `domain_name`, `generated_at`, `production_versions`, `pending_approvals`, `feedback_trends`, `release_blockers`, computed `release_ready`.
- `GovernanceReportService.build_report(knowledge_base_id, domain_name)`.

Use only public repository/service protocols. Treat review states `incomplete`, `misleading`, `unsupported`, `rejected`, and `regeneration_requested` as challenged.

- [x] **Step 4: Run focused GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/governance/test_service.py -q
PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright
```

Result:

- `uv run --project backend pytest backend/tests/governance/test_service.py -q`: 4 passed.
- `uv run --project backend ruff check --no-cache backend/governance backend/tests/governance`: passed after removing an unused test import surfaced by the red gate.
- `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright`: 0 errors, 0 warnings.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/governance backend/tests/governance/test_service.py
git commit -m "feat: add governance report service"
```

Result:

- Commit `0b23f42 feat: add governance report service`.
- Spec review found first-page-only inventory for playbooks, workflow definitions, and explanation reviews. Added pagination regression tests and commit `cbb2b54 fix: paginate governance report inputs`; focused tests now pass with 6 tests, Ruff clean, and Pyright 0 errors/warnings.

### Task 2: Governance Report API Route

**Files:**
- Modify: `backend/api/contracts.py`
- Create: `backend/api/routers/governance.py`
- Modify: `backend/api/app.py`
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/api/test_governance_router.py`

- [x] **Step 1: Write failing API tests**

Create route tests that assert:

- `GET /knowledgebases/kb-governance/governance/report` returns report fields for an authorized viewer.
- An out-of-scope user receives `404`.
- The response includes a blocking `missing_playbook_baseline` blocker when no playbook snapshot exists.

- [x] **Step 2: Run focused RED**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_governance_router.py -q
```

Expected: FAIL with `404 Not Found` or import failure because the route is not registered.

Result:

- `uv run --project backend pytest backend/tests/api/test_governance_router.py -q`: failed with authorized governance report requests returning `404 Not Found`.

- [x] **Step 3: Implement route, contracts, and DI**

Add Pydantic response contracts mirroring the governance models. Add a viewer-gated router at:

```text
GET /knowledgebases/{knowledge_base_id}/governance/report
```

Resolve the KB using the same authorization pattern as playbooks/workflow definitions, derive `domain_name` from the KB, call `GovernanceReportService`, and project the report into `GovernanceReportResponse`.

- [x] **Step 4: Run focused GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_governance_router.py backend/tests/governance/test_service.py -q
PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright
```

Result:

- `uv run --project backend pytest backend/tests/api/test_governance_router.py backend/tests/governance/test_service.py -q`: 9 passed.
- `uv run --project backend ruff check --no-cache backend/governance backend/api/routers/governance.py backend/tests/governance backend/tests/api/test_governance_router.py`: passed.
- `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright`: 0 errors, 0 warnings.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/api/contracts.py backend/api/routers/governance.py backend/api/app.py backend/api/dependencies.py backend/tests/api/test_governance_router.py
git commit -m "feat: expose governance report API"
```

Result:

- Commit `5206036 feat: expose governance report API`.
- Code-quality review found stale generated OpenAPI/frontend contracts, missing `api.contracts.__all__` exports, and missing Pyright include scope. Fixed in commit `1265473 fix: close governance API contract gates`; verification: 24 focused backend tests passed, Ruff clean, Pyright 0 errors/warnings, and `npm run build` passed.

### Task 3: Frontend Governance API And Dashboard

**Files:**
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`
- Create: `chili_app/src/api/governance.ts`
- Create: `chili_app/src/api/__tests__/governance.test.ts`
- Create: `chili_app/src/pages/GovernancePage.tsx`
- Create: `chili_app/src/pages/__tests__/GovernancePage.test.tsx`
- Modify: `chili_app/src/app/router.tsx`
- Modify: `chili_app/src/app/access.ts`
- Modify: `chili_app/src/components/layout/Sidebar.tsx`

- [x] **Step 1: Regenerate frontend contracts**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api
```

Result:

- Completed during Task 2 review fix in commit `1265473 fix: close governance API contract gates`.
- Verified generated route and schema references with `rg -n "governance/report|GovernanceReportResponse|GovernanceFeedbackTrendResponse" chili_app/openapi.json chili_app/src/lib/api/schema.ts backend/api/contracts.py backend/pyproject.toml`.

- [x] **Step 2: Write failing frontend tests**

Add tests that assert:

- `getGovernanceReport('kb live')` calls `/knowledgebases/kb%20live/governance/report`.
- `governanceReportQueryKey(null)` returns `['governance-report', 'missing']`.
- `GovernancePage` renders no-KB, loading, error, and populated report states.
- The populated page exposes accessible labels for `Release readiness: blocked`, `Published versions`, `Pending approvals`, and `Challenged explanations`.

- [x] **Step 3: Run focused RED**

Run:

```bash
npm run test:run -- src/api/__tests__/governance.test.ts src/pages/__tests__/GovernancePage.test.tsx
```

Expected: FAIL because the API helper and page do not exist.

Result:

- `npm run test:run -- src/api/__tests__/governance.test.ts src/pages/__tests__/GovernancePage.test.tsx`: failed because `../governance` and `../GovernancePage` did not exist.

- [x] **Step 4: Implement API helper, page, route, and navigation mapping**

Implement `useGovernanceReport(knowledgeBaseId)`. Build `GovernancePage` using `SectionHeader`, `Card`, `StatusPill`, `Chip`, `EmptyState`, `LoadingState`, and `ErrorState`. Keep it dense: no hero, no nested cards, no marketing copy.

- [x] **Step 5: Run focused GREEN**

Run:

```bash
npm run test:run -- src/api/__tests__/governance.test.ts src/pages/__tests__/GovernancePage.test.tsx src/app/__tests__/access.test.ts src/components/layout/__tests__/AppShell.test.tsx
npm run build
```

Result:

- First focused run failed on two red gates: `access.test.ts` expected list did not include governance for admin, and duplicate accessible labels made `Release readiness: blocked` ambiguous.
- Fixed both gates by updating the expected admin page set and making repeated section count labels unique.
- `npm run test:run -- src/api/__tests__/governance.test.ts src/pages/__tests__/GovernancePage.test.tsx src/app/__tests__/access.test.ts src/components/layout/__tests__/AppShell.test.tsx`: 43 passed.
- `npm run build`: passed.
- `npm run lint`: passed.

- [x] **Step 6: Commit**

Run:

```bash
git add chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/governance.ts chili_app/src/api/__tests__/governance.test.ts chili_app/src/pages/GovernancePage.tsx chili_app/src/pages/__tests__/GovernancePage.test.tsx chili_app/src/app/router.tsx chili_app/src/app/access.ts chili_app/src/components/layout/Sidebar.tsx
git commit -m "feat: add governance dashboard"
```

Result:

- Commit `31aa0a7 feat: add governance dashboard`.

### Task 4: Config And Documentation Wiring

**Files:**
- Modify: `backend/config/defaults/medicare_fraud.yaml`
- Modify: `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml`
- Modify: `backend/tests/config/test_schema.py`
- Modify: `backend/README.md`
- Modify: `chili_app/README.md`
- Modify: `docs/architecture.md`

- [x] **Step 1: Write failing config test**

Add a test that loads both CMS packs and asserts:

- Navigation includes page id `governance` at route `/governance`.
- Supervisor roles include `governance`.
- Analyst roles do not include `governance`.

- [x] **Step 2: Run focused RED**

Run:

```bash
uv run --project backend pytest backend/tests/config/test_schema.py -q
```

Expected: FAIL because the CMS packs do not expose the governance page.

Result:

- `uv run --project backend pytest backend/tests/config/test_schema.py::test_cms_packs_expose_governance_to_supervisors_only -q`: failed for both CMS packs with `KeyError: 'governance'`.

- [x] **Step 3: Update CMS pack navigation and docs**

Add the governance page to the Medicare fraud and CMS DESynPUF packs with a supervisor-only role assignment. Document the new backend module, API route, and frontend dashboard in the relevant README/architecture sections.

- [x] **Step 4: Run focused GREEN**

Run:

```bash
uv run --project backend pytest backend/tests/config/test_schema.py -q
PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright
rg -n "governance|SAFE-CMS-020|/governance" backend/README.md chili_app/README.md docs/architecture.md
```

Result:

- `uv run --project backend pytest backend/tests/config/test_schema.py::test_cms_packs_expose_governance_to_supervisors_only backend/tests/config/test_loader.py::test_all_defaults_load_successfully -q`: 6 passed.
- `uv run --project backend ruff check --no-cache backend/tests/config/test_schema.py`: passed.
- `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright`: first sandboxed run failed on uv cache filesystem access; escalated rerun found optional-member test issues; after explicit assertions, rerun passed with 0 errors, 0 warnings.

- [x] **Step 5: Commit**

Run:

```bash
git add backend/config/defaults/medicare_fraud.yaml backend/config/defaults/medicare_fraud_cms_desynpuf.yaml backend/tests/config/test_schema.py backend/README.md chili_app/README.md docs/architecture.md
git commit -m "docs: wire governance dashboard into cms packs"
```

Result:

- Commit `6271592 docs: wire governance dashboard into cms packs`.

### Task 5: Live Stack And E2E Governance Smoke

**Files:**
- Create: `chili_app/e2e/governance.spec.ts`

- [x] **Step 1: Write failing e2e test**

Add a Playwright test that uses the existing global setup seed, opens `/governance?kb=<seeded kb id>`, and asserts the page shows release readiness plus version/blocker sections.

- [x] **Step 2: Run focused RED**

Run against the Docker-backed stack:

```bash
env -u NO_COLOR -u FORCE_COLOR npm run test:e2e -- e2e/governance.spec.ts
```

Expected before implementation/config completion: FAIL because `/governance` is unavailable or the report endpoint is missing.

Result:

- Because Tasks 3 and 4 had already implemented the route, endpoint, and config by the time this spec was added, the pre-implementation `/governance` unavailable failure was already closed.
- Initial local run still failed before the spec executed because Playwright's webServer availability probe hit sandbox `connect EPERM 127.0.0.1:5173`; this was an environment gate, not an application response.

- [x] **Step 3: Implement minimal e2e wiring fixes**

Fix only route/config/test wiring gaps revealed by the red test. Do not mock API routes in Playwright.

Result:

- Rebuilt/recreated the dev-compose `api` and `app` services after the new route/config commits so e2e exercised current code at `localhost:8000` and `localhost:5173`.
- Corrected an accidental default-compose rebuild by restoring `docker-compose.dev.yaml` services on `:5173`.

- [x] **Step 4: Run focused GREEN**

Run:

```bash
env -u NO_COLOR -u FORCE_COLOR npm run test:e2e -- e2e/governance.spec.ts
npm run lint
```

Result:

- Sandboxed Playwright run failed with `connect EPERM 127.0.0.1:5173`; escalated rerun passed: 1 Chromium test passed, with e2e teardown deleting the seeded KB.
- `npm run lint`: passed.

Commit:

- `956759e test: add governance dashboard e2e smoke`.

### Task 6: Final Verification And Branch Completion

**Files:**
- Modify: `docs/superpowers/plans/2026-08-05-safe-cms-020-governance-evals.md`

- [x] **Step 1: Run frontend gates**

Run:

```bash
npm run test:run
npm run lint
npm run build
```

Result:

- `npm run test:run`: 119 files passed, 1002 tests passed.
- `npm run lint`: passed.
- `npm run build`: passed.

- [x] **Step 2: Run backend gates**

Run:

```bash
uv run --project backend pytest backend/tests/governance backend/tests/api/test_governance_router.py backend/tests/api/test_app.py backend/tests/config/test_schema.py -q
PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright
```

Result:

- `uv run --project backend pytest backend/tests/governance backend/tests/api/test_governance_router.py backend/tests/api/test_app.py backend/tests/config/test_schema.py -q`: 136 passed.
- `uv run --project backend ruff check --no-cache backend/governance backend/api/routers/governance.py backend/tests/governance backend/tests/api/test_governance_router.py backend/tests/config/test_schema.py`: passed.
- `PYRIGHT_PYTHON_FORCE_VERSION=latest uv run --project backend pyright`: 0 errors, 0 warnings.

- [x] **Step 3: Run browser/live-stack gate**

Run:

```bash
docker compose -f docker-compose.dev.yaml ps
curl -sS http://localhost:8000/health
env -u NO_COLOR -u FORCE_COLOR npm run test:e2e -- e2e/governance.spec.ts e2e/dashboard-kb-scope.spec.ts
```

Result:

- `docker compose -f docker-compose.dev.yaml ps`: API/app/data services healthy or running; app on `:5173`, API on `:8000`.
- `curl -sS http://localhost:8000/health`: `{"status":"ok"}`.
- `env -u NO_COLOR -u FORCE_COLOR npm run test:e2e -- e2e/governance.spec.ts e2e/dashboard-kb-scope.spec.ts`: 4 Chromium tests passed; e2e teardown deleted 3/3 run-created KBs.

- [x] **Step 4: Run whitespace and branch checks**

Run:

```bash
git diff --check
git status --short --branch
```

Result:

- `git diff --check`: passed.
- `git status --short --branch`: clean on `safe-cms-020-governance-evals`.

- [x] **Step 5: Commit final plan status**

Run:

```bash
git add docs/superpowers/plans/2026-08-05-safe-cms-020-governance-evals.md
git commit -m "docs: update safe cms 020 plan status"
```

Result:

- Completed by the plan-status commit containing this update.

- [ ] **Step 6: Finish branch into prod only**

Use the finishing-a-development-branch workflow with local `prod` as the integration target. Fetch and push only `origin/prod`; do not merge into or push `origin/main`.
