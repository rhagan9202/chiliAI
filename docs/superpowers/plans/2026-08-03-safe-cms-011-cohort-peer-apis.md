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

- [ ] Add versioned cohort definitions that can reference entity type, peer metric, grouping dimensions, exclusions, and minimum cohort size.
- [ ] Keep definitions KB/domain scoped through `DomainConfig`.
- [ ] Reject invalid cohort definitions through config validation.
- [ ] Add CMS examples for specialty/geography/service-mix comparisons.

## Task 4: Cohort Membership And Distribution API

**Files:**
- Modify/create peerstats read service and Postgres adapter methods
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/routers/analytics.py`
- Modify: API tests
- Regenerate frontend contracts

- [ ] Expose cohort definitions and membership/exclusion logic.
- [ ] Expose peer metric distribution summaries such as p50/p90 and count.
- [ ] Return low-confidence states for small cohorts.
- [ ] Verify Postgres query shape and performance smoke.

## Task 5: UI Peer Comparison Widgets

**Files:**
- Modify/create frontend analytics API wrapper
- Modify: cockpit, queue preview, and dashboard drilldown surfaces
- Add component/Vitest/Playwright coverage

- [ ] Render peer-comparison widgets with entity value, peer median/p90, z-score, percentile, and confidence.
- [ ] Omit or degrade cleanly for domains without peerstats capability/data.
- [ ] Preserve KB and entity route state.
- [ ] Verify no mobile/desktop text overlap.

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
