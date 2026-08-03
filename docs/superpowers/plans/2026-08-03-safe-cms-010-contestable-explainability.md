# SAFE-CMS-010 Contestable Explainability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let analysts review, challenge, annotate, and lifecycle-track generated explanations and feature attributions without mutating the original evidence pack.

**Architecture:** Add a KB-scoped explanation-review domain beside `analytics/explainability`, backed first by an in-memory repository and then a durable Postgres adapter. Reviews attach to evidence-pack subtargets (`narrative`, `narrative_section`, `feature_attribution`, `evidence_item`, or `provenance_reference`) and emit audit events through SAFE-CMS-009. UI controls read/write the review projection through the evidence-pack surface and show review status in the cockpit/case dossier path.

**Tech Stack:** FastAPI, Pydantic, repository protocols, Postgres migrations, React Query, generated OpenAPI contracts, Vitest, Playwright, pyright, ruff.

---

## Context

- Existing generated explanations are persisted as `shared.types.EvidencePack` through `analytics.explainability.repository.EvidencePackRepository`.
- `backend/api/routers/evidence.py` currently exposes read/export/provenance endpoints only.
- `chili_app/src/components/investigation/EvidencePackViewer.tsx` renders narrative sections, feature attributions, evidence items, and provenance references.
- SAFE-CMS-009 already provides a typed audit writer and failure-isolated audit service.
- Contestability must not overwrite the generated explanation text or provenance. It adds human review state beside those artifacts.

## Guardrails

- Keep review records append/update scoped by KB and evidence pack; never rewrite the original evidence pack.
- Require structured reasons for negative/challenge states; do not ship thumbs-only feedback.
- Store comment snippets and reason codes; avoid persisting credentials, tokens, or raw secrets in audit metadata.
- Make regeneration requests queued/pending state only in this sprint; do not call LLM/model generation synchronously from a UI click.
- Preserve non-CMS domain behavior. Review labels are domain-neutral.

## Task 1: Explanation Review Domain Contract And In-Memory Store

**Files:**
- Create: `backend/analytics/explainability/reviews.py`
- Create: `backend/tests/analytics/explainability/test_reviews.py`

- [x] Add typed models for review targets, states, reason codes, create/update requests, stored review records, and paged queries.
- [x] Add `ExplanationReviewRepository` protocol and in-memory adapter with KB/evidence-pack filtering.
- [x] Add `ExplanationReviewService` validation: negative states require at least one reason, comments are trimmed and bounded, and target ids are KB/evidence-pack scoped strings.
- [x] Verify with focused tests, pyright, and ruff.

**Steps:**

1. Write failing tests in `backend/tests/analytics/explainability/test_reviews.py` proving:
   - creating an `unsupported` review without reasons raises `ValueError`;
   - creating a useful review stores the trimmed comment and returns newest-first in KB/evidence-pack queries;
   - updating the same target preserves the original `created_at` and advances `updated_at`;
   - querying another KB/evidence pack does not leak reviews.
2. Run RED: `uv run --project backend pytest backend/tests/analytics/explainability/test_reviews.py -q`; expected failure: `ModuleNotFoundError` for `analytics.explainability.reviews`.
3. Implement `backend/analytics/explainability/reviews.py` with Pydantic models, protocol, `InMemoryExplanationReviewRepository`, and `ExplanationReviewService`.
4. Run GREEN:
   - `uv run --project backend pytest backend/tests/analytics/explainability/test_reviews.py -q`
   - `uv run --project backend ruff check backend/analytics/explainability/reviews.py backend/tests/analytics/explainability/test_reviews.py`
   - `uv run --project backend pyright backend/analytics/explainability/reviews.py backend/tests/analytics/explainability/test_reviews.py`
5. Commit: `git commit -m "Add SAFE-CMS-010 explanation review domain"`.

**Notes:**
- Added `analytics.explainability.reviews` with domain-neutral review target/state/reason models, a repository protocol, an in-memory repository, and `ExplanationReviewService`.
- Reviews upsert by `(knowledge_base_id, evidence_pack_id, target_type, target_id)`, preserve `created_at`, advance `updated_at`, increment `update_count`, and list newest-first.
- RED: `uv run --project backend pytest backend/tests/analytics/explainability/test_reviews.py -q` failed during collection with `ModuleNotFoundError: No module named 'analytics.explainability.reviews'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/analytics/explainability/test_reviews.py -q`: 4 passed.
  - `uv run --project backend ruff check backend/analytics/explainability/reviews.py backend/tests/analytics/explainability/test_reviews.py`: passed.
  - `uv run --project backend pyright backend/analytics/explainability/reviews.py backend/tests/analytics/explainability/test_reviews.py`: 0 errors.

## Task 2: Evidence Review API And Audit Hooks

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/routers/evidence.py`
- Create/modify: `backend/tests/api/test_evidence_reviews.py`
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`
- Modify: `chili_app/src/api/contracts.ts`

- [x] Register `GET /evidence-packs/{evidence_pack_id}/reviews` and `POST /evidence-packs/{evidence_pack_id}/reviews`.
- [x] Require `viewer` for reads and `analyst` for creates/updates.
- [x] Reject missing evidence packs and cross-KB writes.
- [x] Emit `explanation.review.create` or `explanation.review.update` audit events with target, state, reason count, and comment-present metadata only.
- [x] Export OpenAPI and regenerate frontend contracts.

**Steps:**

1. Write failing API tests proving create/list, negative-reason validation, cross-KB isolation, missing evidence-pack 404, and audit event emission without raw comment text.
2. Run RED: `uv run --project backend pytest backend/tests/api/test_evidence_reviews.py -q`; expected failure: route 404 or missing contracts.
3. Add request/response contracts and dependency helpers, wire the evidence router, and reuse `get_evidence_pack_repository` for existence checks.
4. Run GREEN:
   - `uv run --project backend pytest backend/tests/api/test_evidence_reviews.py backend/tests/api/test_audit_router.py -q`
   - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/routers/evidence.py backend/tests/api/test_evidence_reviews.py`
   - `uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/api/routers/evidence.py backend/tests/api/test_evidence_reviews.py`
   - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`
   - `cd chili_app && npm run codegen:api`
5. Commit: `git commit -m "Add SAFE-CMS-010 evidence review API"`.

**Notes:**
- Added evidence-pack review request/list/response contracts and generated frontend schema aliases.
- Added `GET /evidence-packs/{evidence_pack_id}/reviews` and `POST /evidence-packs/{evidence_pack_id}/reviews`; reads are viewer-gated and writes are analyst-gated.
- Evidence review writes prove the evidence pack exists in the requested KB before recording review state, so same-id evidence packs in another KB do not leak reviews.
- Review create/update emits sanitized `explanation.review.*` audit events with target, state, reason count, comment-present flag, review id, and update count; raw comments are omitted from audit before/after/metadata.
- RED: `uv run --project backend pytest backend/tests/api/test_evidence_reviews.py -q` failed with 404s for the missing `/evidence-packs/{evidence_pack_id}/reviews` routes.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_evidence_reviews.py backend/tests/api/test_audit_router.py -q`: 10 passed.
  - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/routers/evidence.py backend/tests/api/test_evidence_reviews.py`: passed.
  - `uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/api/routers/evidence.py backend/tests/api/test_evidence_reviews.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `cd chili_app && npm run codegen:api`: passed.
  - `cd chili_app && pnpm build`: passed with the existing Vite large-chunk warning.

## Task 3: Durable Review Persistence

**Files:**
- Create: `backend/analytics/explainability/adapters/reviews_postgres.py`
- Create: `backend/database/migrations/versions/<next>_explanation_reviews.py`
- Modify: `backend/database/migrations/snapshots/head.sql`
- Modify: `backend/api/dependencies.py`
- Create/modify: `backend/tests/analytics/explainability/test_reviews_postgres.py`

- [x] Add `explanation_reviews` table with indexes on `(knowledge_base_id, evidence_pack_id, updated_at DESC)` and `(knowledge_base_id, state, updated_at DESC)`.
- [x] Persist target type/id, state, reasons, comment snippet, actor, timestamps, and update count.
- [x] Use Postgres when the app has a connection provider; otherwise use in-memory for tests/dev without Postgres.
- [x] Verify migrations and repository parity.

**Steps:**

1. Write failing Postgres adapter tests for create/update/list ordering and KB isolation.
2. Run RED: `uv run --project backend pytest backend/tests/analytics/explainability/test_reviews_postgres.py -q`; expected failure: missing adapter.
3. Implement the adapter and migration, then wire dependency selection in `get_explanation_review_service`.
4. Run GREEN:
   - `uv run --project backend pytest backend/tests/analytics/explainability/test_reviews.py backend/tests/analytics/explainability/test_reviews_postgres.py backend/tests/api/test_evidence_reviews.py -q`
   - `scripts/ci_migration_check.sh --update-snapshot`
   - `scripts/ci_migration_check.sh`
   - `uv run --project backend ruff check backend/analytics/explainability/reviews.py backend/analytics/explainability/adapters/reviews_postgres.py backend/api/dependencies.py backend/database/migrations/versions/<migration>.py backend/tests/analytics/explainability/test_reviews_postgres.py`
   - `uv run --project backend pyright backend/analytics/explainability/reviews.py backend/analytics/explainability/adapters/reviews_postgres.py backend/api/dependencies.py backend/tests/analytics/explainability/test_reviews_postgres.py`
5. Commit: `git commit -m "Persist SAFE-CMS-010 explanation reviews"`.

**Notes:**
- Added `analytics.explainability.adapters.reviews_postgres.PostgresExplanationReviewRepository` backed by `explanation_reviews`.
- Added migration `0017_explanation_reviews` with KB/evidence/target uniqueness, state/target check constraints, durable review fields, and the required KB-pack/state updated-at indexes.
- `get_explanation_review_service` now chooses Postgres when `get_connection_provider()` is available and falls back to in-memory otherwise; dependency regression tests cover both branches.
- RED: `uv run --project backend pytest backend/tests/analytics/explainability/test_reviews_postgres.py -q` failed during collection with `ModuleNotFoundError: No module named 'analytics.explainability.adapters.reviews_postgres'`.
- GREEN:
  - `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili uv run --project backend pytest backend/tests/analytics/explainability/test_reviews.py backend/tests/analytics/explainability/test_reviews_postgres.py backend/tests/api/test_evidence_reviews.py -q`: 13 passed.
  - `scripts/ci_migration_check.sh --update-snapshot`: passed and regenerated `backend/database/migrations/snapshots/head.sql`.
  - `scripts/ci_migration_check.sh`: passed.
  - `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili uv run --project backend pytest backend/tests/analytics/explainability/test_reviews.py backend/tests/analytics/explainability/test_reviews_postgres.py backend/tests/api/test_evidence_reviews.py backend/tests/api/test_dependencies.py -q -k "reviews or explanation_review_service"`: 15 passed, 60 deselected.
  - `uv run --project backend ruff check backend/analytics/explainability/reviews.py backend/analytics/explainability/adapters/reviews_postgres.py backend/api/dependencies.py backend/database/migrations/versions/0017_explanation_reviews.py backend/tests/analytics/explainability/test_reviews_postgres.py backend/tests/api/test_dependencies.py`: passed.
  - `uv run --project backend pyright backend/analytics/explainability/reviews.py backend/analytics/explainability/adapters/reviews_postgres.py backend/api/dependencies.py backend/tests/analytics/explainability/test_reviews_postgres.py backend/tests/api/test_dependencies.py`: 0 errors.

## Task 4: Evidence Viewer Review Controls

**Files:**
- Create/modify: `chili_app/src/api/explanationReviews.ts`
- Modify: `chili_app/src/api/contracts.ts`
- Modify: `chili_app/src/components/investigation/EvidencePackViewer.tsx`
- Create/modify: `chili_app/src/components/investigation/__tests__/EvidencePackViewer.test.tsx`
- Modify: `chili_app/src/pages/AlertFeedPage.tsx`
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`

- [ ] Add React Query hooks for listing and submitting explanation reviews.
- [ ] Render compact review controls for narrative and feature attribution targets.
- [ ] Require reason categories when an analyst selects `incomplete`, `misleading`, or `unsupported`.
- [ ] Show current review status without duplicating the generated explanation text.

**Steps:**

1. Write failing Vitest coverage that renders review controls, blocks unsupported feedback without a reason, submits a supported review payload, and shows current status returned from the hook.
2. Run RED: `cd chili_app && npx vitest run src/components/investigation/__tests__/EvidencePackViewer.test.tsx -t "explanation review"`.
3. Implement the hooks and minimal UI controls; thread `knowledgeBaseId` and `evidencePackId` from Alert Feed and Workbench.
4. Run GREEN:
   - `cd chili_app && npx vitest run src/components/investigation/__tests__/EvidencePackViewer.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`
   - `cd chili_app && pnpm build`
5. Commit: `git commit -m "Add SAFE-CMS-010 explanation review controls"`.

## Task 5: Dossier/Cockpit Review Status And Browser Flow

**Files:**
- Modify: `backend/api/dependencies.py`
- Modify: `backend/tests/api/test_phase5_stateful_routes.py`
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Modify: `chili_app/src/pages/__tests__/CaseManagementPage.test.tsx`
- Create/modify: `chili_app/e2e/explanation-review.spec.ts`

- [ ] Include explanation-review status summaries in case dossier read/export projections.
- [ ] Surface challenged explanation status in Case Management and the Workbench evidence flow.
- [ ] Verify an analyst can challenge an explanation, reopen the case/workbench path, and see the status persist.

**Steps:**

1. Write failing backend dossier tests asserting review summaries appear in JSON/Markdown export without raw secret-like comments.
2. Write failing frontend/e2e tests for review persistence across case dossier and cockpit navigation.
3. Implement the minimal read-model and UI summaries.
4. Run GREEN:
   - `uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_case_dossier_includes_explanation_review_status -q`
   - `cd chili_app && npx vitest run src/pages/__tests__/CaseManagementPage.test.tsx src/components/investigation/__tests__/EvidencePackViewer.test.tsx`
   - Start the dev stack with `CHILI_CONFIG_PATH=/app/config/defaults/medicare_fraud.yaml CHILI_DEV_ANONYMOUS_ROLE=analyst docker compose -f docker-compose.dev.yaml up -d --build`, then run `cd chili_app && pnpm exec playwright test e2e/explanation-review.spec.ts`, then tear down with `docker compose -f docker-compose.dev.yaml down -v`.
5. Commit: `git commit -m "Surface SAFE-CMS-010 review status in dossiers"`.

## Review Gates

- Review after Task 1 before adding API/audit wiring.
- Review after Task 3 before frontend controls.
- Review after Task 5 before backlog status changes.

## Definition Of Done

- Analysts can record structured review state for generated explanation targets.
- Negative/challenge feedback requires reason codes.
- Review data is KB/evidence-pack scoped, durable, and queryable.
- Review mutations emit sanitized audit events.
- Evidence, cockpit, and dossier surfaces show review status without mutating generated evidence.
- Focused backend/frontend tests, OpenAPI/codegen, migration checks, Playwright browser flow, pyright/ruff/build, and whitespace checks pass.
