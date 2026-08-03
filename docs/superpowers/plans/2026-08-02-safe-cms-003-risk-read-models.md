# SAFE-CMS-003 Production Risk Read Models Implementation Plan

**Owner:** Codex
**Date:** 2026-08-02
**Branch:** `fix/normalize-kb-query-param`
**Parent dependencies:** `SAFE-CMS-001`, `SAFE-CMS-002` through commit `41efb7e`

## Goal

Create fast, queryable, projection-backed risk read models for alert queues, dashboard rollups, entity summaries,
and cohort-oriented filters without making frontend pages assemble risk state from unrelated endpoints.

## Architecture

Start with an explicit domain-neutral projection seam in `analytics.risk`. The current `/analytics/risk-scores`
surface ranks latest `risk_score_history` rows, but it has no offset pagination, score freshness, top typologies,
evidence/case/alert refs, or rebuild contract. Add a projection model/repository/service first, then adapt the
API and frontend hooks to consume that stable shape. Keep writes idempotent and rebuildable so later worker/event
integration can project from score runs, feature values, alerts, evidence packs, and cases.

## Current Inventory

- `backend/analytics/risk/adapters/postgres.py` writes `risk_score_history` and reads latest scores by entity.
- `backend/analytics/risk/service_models.py` exposes `RiskScoreListRequest` with `knowledge_base_id`,
  optional `entity_type`, and `limit` only.
- `backend/api/routers/analytics.py` exposes `/analytics/risk-scores` and `/analytics/risk-scores/{entity_id}`.
- `chili_app/src/api/analytics.ts` wraps risk-score list/detail with generated contracts and simple filters.
- Alert feed and dashboard pages already consume alerts, analytics overview, and risk-score lists, but they still
  lack score age, typology, case/evidence refs, and projection rebuild state.

## Task 1: Risk Projection Domain Model And Repository

**Files:**
- Create: `backend/analytics/risk/projections.py`
- Create or modify: in-memory projection repository/adapters
- Test: `backend/tests/analytics/risk/test_risk_projections.py`

- [x] **Step 1: Write failing projection repository tests**

Cover upsert by `(knowledge_base_id, entity_id)`, detached copies, pagination with offset, sort by score and
freshness, filters for entity type, risk level, typology id, status, and score age.

- [x] **Step 2: Implement projection models and in-memory repository**

Projection rows should include `knowledge_base_id`, `entity_id`, `entity_type`, `overall_score`, `risk_level`,
`top_typology_ids`, `alert_ids`, `case_ids`, `evidence_pack_ids`, `score_run_id`, `model_version`,
`catalog_version`, `scored_at`, `updated_at`, and `status`.

- [x] **Step 3: Run focused projection tests**

Expected: projection repository tests pass without changing existing risk-score API behavior.

Task 1 review notes:

- Added `RiskProjectionRow`, `RiskProjectionQuery`, `RiskProjectionPage`, and
  `InMemoryRiskProjectionRepository`.
- Tests cover natural-key upsert by `(knowledge_base_id, entity_id)`, detached copies, same entity id across
  multiple KBs, score ranking, freshness tie-breaks, offset pagination, operator filters, score-age filtering,
  and timezone-aware timestamp validation.
- Review found naive `scored_at` values could break age filtering and local-time sorting; fixed by requiring
  timezone-aware `scored_at` and `updated_at`.
- Focused verification passed: `backend/tests/analytics/risk/test_risk_projections.py -q` passed with 7 tests,
  `compileall backend/analytics/risk` passed, and `git diff --check` passed.
- Broader `backend/tests/analytics/risk -q` ran 42 non-Postgres tests but failed two existing
  `test_postgres_history_store.py` tests because local `postgresql://chili:chili@localhost:5432/chili_test`
  was not reachable in this environment.

## Task 2: Projection Writer And Rebuild Service

**Files:**
- Modify/create: `backend/analytics/risk/projection_service.py`
- Test: focused service tests

- [x] **Step 1: Write failing service tests**

Cover idempotent projection upsert from risk assessments, feature values/typologies, score-run metadata, alert
refs, case refs, and evidence refs. Cover rebuild by KB and no-op behavior for unchanged rows.

- [x] **Step 2: Implement writer/rebuild service**

Keep the first rebuild in-process and repository-backed. Worker/event fan-in can follow after the projection
contract is stable.

- [x] **Step 3: Run focused service tests**

Expected: projection writer/rebuild tests pass and existing risk tests still pass.

Task 2 review notes:

- Added `RiskProjectionService`, `RiskProjectionWriteRequest`, write/rebuild result models, and
  `RiskProjectionRepositoryProtocol`.
- `project_assessment` writes one projection row from `RiskScoredReference`, feature values, feature-to-typology
  mapping, score-run/model/catalog versions, alert/case/evidence refs, and status.
- Projection writes are no-ops when the computed row is unchanged.
- Rebuild replaces KB-scoped projection rows and preserves other KBs.
- Review found rebuild compared only the first 500 rows and could falsely no-op; fixed with repository
  `list_all(knowledge_base_id)` and regression coverage over 501 rows.
- Review found typology projection over-included unrelated feature values; fixed by requiring same KB, same entity,
  same entity type, and feature ids present in scored factors.
- Focused verification passed: projection repository/service tests passed with 15 tests; non-integration
  `backend/tests/analytics/risk -m "not integration" -q` passed with 53 tests and 2 integration tests deselected;
  `compileall backend/analytics/risk` and `git diff --check` passed.

## Task 3: API Contract Expansion

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/routers/analytics.py`
- Modify: `backend/api/dependencies.py`
- Test: focused API/router tests

- [x] **Step 1: Add API tests for paginated/filterable risk projections**

Cover `limit`, `offset`, entity type, risk level, typology id, status, max score age, and stable page metadata.

- [x] **Step 2: Add projection-backed routes/contracts**

Prefer expanding `/analytics/risk-scores` only if backward compatibility is preserved. Otherwise add a new
projection-specific route and migrate frontend consumers deliberately.

- [x] **Step 3: Add rebuild command/API seam**

Expose a guarded rebuild service boundary for operators; avoid long-running rebuilds inside request handlers.

Task 3 review notes:

- Added `RiskProjectionItemResponse`, `RiskProjectionListResponse`,
  `RiskProjectionRebuildRequest`, and `RiskProjectionRebuildResponse`.
- Added additive `/analytics/risk-projections` and `/analytics/risk-projections/rebuild`
  routes; `/analytics/risk-scores` remains unchanged for backward compatibility.
- Projection reads support `knowledge_base_id`, `entity_type`, `risk_level`,
  `typology_id`, `status`, `max_score_age_hours`, `as_of`, `limit`, and `offset`.
- Added route tests for projection metadata, offset pagination, operator facets,
  isolated score-age filtering, OpenAPI query/body/response contracts, route role
  markers, naive `as_of` rejection, and configured/unconfigured rebuild behavior.
- Review found the first rebuild route was misleading because it rebuilt from the
  same repository snapshot. Fixed by adding `RiskProjectionRebuildSourceProtocol`
  and failing closed with 503 until an authoritative rebuild source is configured.
- Review found default projection storage could look production-durable while
  still in-memory. Clarified DI docs and kept rebuild gated so frontend migration
  cannot assume durable projections before the runtime writer adapter lands.
- Review found naive `as_of` could escape as a route-body validation error; fixed
  with explicit 422 handling before constructing `RiskProjectionQuery`.
- Attempted request-level `TestClient` coverage for the new endpoints, but this
  checkout still hangs on TestClient request execution for these routes. Replaced
  the hanging tests with direct route tests plus OpenAPI and role-marker checks.
- Focused verification passed: 11 projection API tests, 15 projection
  repository/service tests, non-integration `backend/tests/analytics/risk -m "not
  integration"` with 53 tests and 2 deselected, `compileall backend/api
  backend/analytics/risk`, OpenAPI export, frontend codegen, `pnpm build`, `git
  diff --check`, and `python3 scripts/backlog_consistency.py --check`.

## Task 4: Frontend Hooks And Consumer Migration

**Files:**
- Regenerate OpenAPI/frontend types.
- Modify: `chili_app/src/api/analytics.ts`
- Modify: dashboard/alert/entity consumers as needed.
- Test: focused API hook and page/component tests.

- [x] **Step 1: Add frontend API wrapper tests**

Cover serialized filters, pagination, and score freshness fields.

- [x] **Step 2: Migrate first consumer to projection-backed risk rows**

Start with dashboard risk ranking because it already uses `/analytics/risk-scores`.

- [x] **Step 3: Run frontend tests and build**

Expected: focused frontend tests and `pnpm build` pass.

Task 4 review notes:

- Added frontend risk projection contract aliases, filter type, query key, fetcher, and hook.
- Projection wrapper tests cover camelCase-to-query serialization for entity type, risk level,
  typology, status, max score age, `as_of`, limit, and offset, plus collection cache keys.
- Migrated the dashboard Top risk entities panel from `useRiskScores` to `useRiskProjections`
  with `{ knowledgeBaseId, limit: 5, offset: 0 }`.
- Dashboard rows now render projection metadata: status, top typology, scored date, and score.
- Review found no blocking frontend API or dashboard migration issues. Low review gaps were
  closed by expanding the query-key test and adding a ready-KB empty projection state test.
- Focused verification passed: `npm run test:run -- src/api/__tests__/analytics.test.ts
  src/pages/__tests__/DashboardPage.test.tsx` with 29 tests, `pnpm build`, `git diff --check`,
  and `python3 scripts/backlog_consistency.py --check`.

## Task 5: Verification And Closeout

- [x] Backend focused tests.
- [x] Frontend focused tests/build if contracts changed.
- [x] `git diff --check`
- [x] `python3 scripts/backlog_consistency.py --check`
- [x] Update backlog and this plan with verification evidence.

Task 5 closeout notes:

- Backlog updated in `docs/project/planning/backlog.md`: `SAFE-CMS-002` marked done and
  `SAFE-CMS-003` marked in progress with the landed projection domain/service/API/dashboard
  slice and the remaining durable projection adapter/rebuild source production gap.
- Branch commits pushed for this slice: `235a6fc` projection writer service, `87bd91d`
  risk projection API, and `627dd6f` dashboard migration to risk projections.
- Final verified branch sync after Task 4: `git rev-list --left-right --count
  HEAD...origin/fix/normalize-kb-query-param` returned `0 0`.
- Remaining SAFE-CMS-003 production DoD: choose and implement durable risk projection storage
  and an authoritative rebuild source so `/analytics/risk-projections/rebuild` can execute
  rather than returning the intentional 503 guard.

## Review Gates

- Review after Task 1 before API changes.
- Review after Task 3 before frontend migration.
- Review after Task 4 before commit/push.

## Open Questions

- Whether Postgres should use a physical projection table first or a materialized view over `risk_score_history`
  plus alert/case/evidence tables. Default for Task 1 is repository abstraction plus in-memory implementation.
- Exact score-age filter semantics: likely `scored_at >= now - max_age_hours`, but API should avoid server-local
  timezone ambiguity.
- Whether `critical` risk level is derived from current alert severity, risk score threshold, or typology severity.
