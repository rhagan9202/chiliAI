# SAFE-CMS-011 Cohort And Peer-Analysis APIs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose cohort construction and peer-comparison analytics as first-class, KB-scoped APIs and UI surfaces so analysts can compare an entity against appropriate peers instead of reading risk scores in isolation.

**Architecture:** Build on the existing `analytics.peerstats` pipeline and `entity_derived_signals` table. The first slices expose latest peer metric context from generated derived signals. Later slices add explicit cohort definitions from domain packs, cohort membership/exclusion explanations, UI widgets, and capability/workflow integration.

**Tech Stack:** FastAPI, Pydantic, peerstats adapters, Postgres-derived signals, generated OpenAPI contracts, React Query, Vitest, Playwright, pyright, ruff.

---

## Context

- `backend/analytics/peerstats` already computes peer-group z-scores and persists `DerivedRiskSignal` rows.
- `entity_derived_signals` stores entity value, peer mean/std, z-score, signal value, weight, rationale, metric name, group key, and interval.
- `backend/api/routers/analytics.py` already exposes risk, projections, timeseries, GNN clusters, and overview endpoints.
- `frontend.28` explicitly records the missing peer-distribution endpoint as the blocker for peer-comparison bars.

## Guardrails

- Keep reusable peer/cohort code domain-neutral; CMS labels and examples belong in domain packs.
- Preserve KB scope on every query; no cross-KB peer leakage.
- Do not recompute expensive peerstats synchronously in the read endpoint.
- Surface low-confidence/small-cohort states instead of hiding missing or degenerate comparisons.
- Use generated OpenAPI contracts; do not hand-write frontend wire DTOs.

## Task 1: Peer-Analysis Domain Read Model

**Files:**
- Create: `backend/analytics/peerstats/peer_analysis.py`
- Modify: `backend/analytics/peerstats/adapters/protocols.py`
- Modify: `backend/analytics/peerstats/adapters/in_memory.py`
- Modify: `backend/analytics/peerstats/adapters/postgres.py`
- Create: `backend/tests/analytics/peerstats/test_peer_analysis.py`

- [x] Add a peer-signal reader protocol over latest entity signals and peer-group signals.
- [x] Add a peer-analysis service that returns latest-per-metric comparison context.
- [x] Compute cohort size and percentile from peer-group signal values.
- [x] Mark small or degenerate cohorts as low confidence.

**Notes:**
- RED: `uv run --project backend pytest backend/tests/analytics/peerstats/test_peer_analysis.py -q` failed with `ModuleNotFoundError: No module named 'analytics.peerstats.peer_analysis'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py -q`: 14 passed.
  - `uv run --project backend ruff check backend/analytics/peerstats/peer_analysis.py backend/analytics/peerstats/adapters/protocols.py backend/analytics/peerstats/adapters/in_memory.py backend/analytics/peerstats/adapters/postgres.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py`: passed.
  - `uv run --project backend pyright backend/analytics/peerstats/peer_analysis.py backend/analytics/peerstats/adapters/protocols.py backend/analytics/peerstats/adapters/in_memory.py backend/analytics/peerstats/adapters/postgres.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py`: 0 errors.

## Task 2: Peer-Analysis API Contract

**Files:**
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Modify: `backend/api/routers/analytics.py`
- Modify: `backend/tests/api/test_analytics_router.py`
- Modify: `chili_app/openapi.json`
- Modify: `chili_app/src/lib/api/schema.ts`

- [x] Register `GET /analytics/peer-analysis/{entity_id}`.
- [x] Require `viewer`.
- [x] Support `knowledge_base_id` and optional `metric` query parameters.
- [x] Return generated response contracts with metric, entity value, peer stats, z-score, percentile, cohort size, and confidence.

**Notes:**
- RED: `uv run --project backend pytest backend/tests/api/test_analytics_router.py -q -k "peer_analysis"` failed during collection with `ImportError: cannot import name 'get_peer_analysis_service'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_analytics_router.py -q -k "peer_analysis"`: 3 passed, 35 deselected.
  - `uv run --project backend pytest backend/tests/api/test_analytics_router.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py -q -m "not integration"`: 51 passed, 1 deselected.
  - Full focused router run without `-m "not integration"` exposed environment state only: `DATABASE_URL` pointed at `postgresql://chili:chili@localhost:5432/chili_test` while Postgres was not running, so the pre-existing integration test `test_query_timeseries_returns_seeded_postgres_rows` failed with connection refused.
  - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/routers/analytics.py backend/analytics/peerstats/peer_analysis.py backend/analytics/peerstats/adapters/protocols.py backend/analytics/peerstats/adapters/in_memory.py backend/analytics/peerstats/adapters/postgres.py backend/tests/api/test_analytics_router.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py`: passed.
  - `uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/api/routers/analytics.py backend/analytics/peerstats/peer_analysis.py backend/analytics/peerstats/adapters/protocols.py backend/analytics/peerstats/adapters/in_memory.py backend/analytics/peerstats/adapters/postgres.py backend/tests/api/test_analytics_router.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `cd chili_app && npm run codegen:api`: passed.

## Task 3: Domain-Pack Cohort Definitions

**Files:**
- Modify: `backend/config/schema.py`
- Modify: CMS domain pack(s)
- Modify: config tests

- [x] Add versioned cohort definitions that can reference entity type, peer metric, grouping dimensions, exclusions, and minimum cohort size.
- [x] Keep definitions KB/domain scoped through `DomainConfig`.
- [x] Reject invalid cohort definitions through config validation.
- [x] Add CMS examples for specialty/geography/service-mix comparisons.

**Notes:**
- Added `PeerCohortDefinitionConfig` and `PeerCohortExclusionConfig` under `PeerStatsConfig.cohorts`.
- Domain cross-reference validation now rejects duplicate cohort ids, unknown peer metrics, cohort/metric entity-type mismatches, and group/exclusion fields missing from the referenced peer metric's record schema.
- Added optional cohort grouping fields and CMS examples for specialty, geography, and service-mix comparisons in the Medicare fraud packs.
- RED: `uv run --project backend pytest backend/tests/config/test_peer_stats_config.py backend/tests/config/test_schema.py -q -k "peer_cohort or peer_stats_config_defaults_empty or cms_pack_declares_peerstats"` failed during collection with `ImportError: cannot import name 'PeerCohortDefinitionConfig'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/config/test_peer_stats_config.py backend/tests/config/test_schema.py backend/tests/config/test_loader.py -q -k "peer_cohort or peer_stats_config_defaults_empty or cms_pack_declares_peerstats"`: 8 passed, 136 deselected.
  - `uv run --project backend pytest backend/tests/config/test_peer_stats_config.py backend/tests/config/test_schema.py backend/tests/config/test_loader.py -q`: 144 passed.
  - `uv run --project backend ruff check backend/config/schema.py backend/tests/config/test_peer_stats_config.py backend/tests/config/test_schema.py backend/tests/config/test_loader.py`: passed.
  - `uv run --project backend pyright backend/config/schema.py backend/tests/config/test_peer_stats_config.py backend/tests/config/test_schema.py backend/tests/config/test_loader.py`: 0 errors.

## Task 4: Cohort Membership And Distribution API

**Files:**
- Modify/create peerstats read service and Postgres adapter methods
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/routers/analytics.py`
- Modify: API tests
- Regenerate frontend contracts

- [x] Expose cohort definitions and membership/exclusion logic.
- [x] Expose peer metric distribution summaries such as p50/p90 and count.
- [x] Return low-confidence states for small cohorts.
- [x] Verify Postgres query shape and performance smoke.

**Notes:**
- Extended peer-analysis metric comparisons with `distribution` summaries (`count`, `minimum`, `p50`, `p90`, `maximum`) and optional `cohort` context.
- Cohort context now includes configured cohort id/label/version, peer metric, group fields, parsed group values, configured exclusions, member ids, and member count.
- `get_peer_analysis_service` now passes active `DomainConfig.peer_stats.cohorts` into the service.
- Added public Postgres peer-group query params/SQL helpers and query-shape tests for exact KB/metric/interval/group filtering.
- RED:
  - `uv run --project backend pytest backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/api/test_analytics_router.py -q -k "cohort_membership or get_peer_analysis_returns_cohort_context"` failed with `TypeError: PeerAnalysisService.__init__() got an unexpected keyword argument 'cohort_definitions'`.
  - `uv run --project backend pytest backend/tests/analytics/peerstats/test_postgres_adapters.py -q -k "peer_group_signal_query"` failed with `ImportError: cannot import name 'PEER_GROUP_SIGNALS_SQL'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/api/test_analytics_router.py -q -k "cohort_membership or get_peer_analysis_returns_cohort_context"`: 2 passed, 40 deselected.
  - `uv run --project backend pytest backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py -q`: 16 passed.
  - `uv run --project backend pytest backend/tests/api/test_analytics_router.py -q -k "peer_analysis"`: 3 passed, 35 deselected.
  - `uv run --project backend pytest backend/tests/api/test_analytics_router.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py -q -m "not integration"`: 53 passed, 1 deselected.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `cd chili_app && npm run codegen:api`: passed.
  - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/routers/analytics.py backend/analytics/peerstats/peer_analysis.py backend/analytics/peerstats/adapters/protocols.py backend/analytics/peerstats/adapters/in_memory.py backend/analytics/peerstats/adapters/postgres.py backend/tests/api/test_analytics_router.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py`: passed.
  - `uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/api/routers/analytics.py backend/analytics/peerstats/peer_analysis.py backend/analytics/peerstats/adapters/protocols.py backend/analytics/peerstats/adapters/in_memory.py backend/analytics/peerstats/adapters/postgres.py backend/tests/api/test_analytics_router.py backend/tests/analytics/peerstats/test_peer_analysis.py backend/tests/analytics/peerstats/test_in_memory_adapters.py backend/tests/analytics/peerstats/test_postgres_adapters.py`: 0 errors.
  - `cd chili_app && pnpm build`: passed with the existing Vite large-chunk warning.
  - With only Postgres running: `uv run --project backend pytest backend/tests/analytics/peerstats/test_postgres_adapters_integration.py backend/tests/api/test_analytics_router.py::test_query_timeseries_returns_seeded_postgres_rows -q`: 3 passed.

## Task 5: UI Peer Comparison Widgets

**Files:**
- Modify/create frontend analytics API wrapper
- Modify: cockpit, queue preview, and dashboard drilldown surfaces
- Add component/Vitest/Playwright coverage

- [x] Render peer-comparison widgets with entity value, peer median/p90, z-score, percentile, and confidence.
- [x] Omit or degrade cleanly for domains without peerstats capability/data.
- [x] Preserve KB and entity route state.
- [x] Verify no mobile/desktop text overlap.

**Notes:**
- Added a generated-contract-backed frontend peer-analysis API helper/query key and `usePeerAnalysis` hook.
- Added `PeerComparisonPanel` for cockpit rendering of entity value, peer median, p90, z-score, percentile, cohort size, confidence, cohort label, and cohort basis.
- Gated cockpit peer comparisons behind `DomainCapabilities.peer_stats`; domains without peerstats do not issue the peer-analysis query.
- Preserved existing KB/entity/alert/evidence route state by rendering the widget inside the investigation cockpit reached from queue and dashboard drilldowns.
- Browser overflow verification exposed an Alert Feed header overflow at 1600px; fixed the root flex/container-query constraint so action controls wrap inside the card instead of forcing row clipping.
- RED:
  - `pnpm test:run src/api/__tests__/analytics.test.ts -t "peer analysis|peer-analysis"` failed with `TypeError: getPeerAnalysis is not a function` and `TypeError: peerAnalysisQueryKey is not a function`.
  - `pnpm test:run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx -t "peer comparison|peer comparisons"` failed because `analyticsCalls.peerAnalysis.at(-1)` was `undefined`.
- GREEN:
  - `pnpm test:run src/api/__tests__/analytics.test.ts -t "peer analysis|peer-analysis"`: 2 passed, 8 skipped.
  - `pnpm test:run src/pages/__tests__/InvestigationWorkbenchPage.test.tsx -t "peer comparison|peer comparisons"`: 2 passed, 36 skipped.
  - `pnpm test:run src/api/__tests__/analytics.test.ts src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: 48 passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `pnpm exec eslint src/api/analytics.ts src/api/contracts.ts src/api/__tests__/analytics.test.ts src/components/analytics/PeerComparisonPanel.tsx src/pages/InvestigationWorkbenchPage.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: passed.
  - `pnpm test:e2e e2e/layout-overflow.spec.ts`: initially failed at 1600px on Alert Feed header overflow; after CSS fix, 5 passed.

## Review Gates

- Review after Task 2 before adding domain-pack cohort definitions.
- Review after Task 4 before frontend widgets.
- Review after Task 5 before backlog closeout.

## Definition Of Done

- Peer analysis returns membership criteria, cohort size, metric distribution, entity value, z-score/percentile, and explanation.
- Cohort definitions are versioned and KB-scoped.
- UI communicates small-cohort and low-confidence states.
- APIs are usable by workflows/capabilities without CMS-only coupling.
- Focused backend/frontend tests, OpenAPI/codegen, pyright/ruff/build, and browser flow pass.
