# SAFE-CMS-012: Entity Identity Resolution and Relationship Scoring

## Goal

Resolve fragmented source identities into canonical graph entities with explainable confidence, steward review states, and graph/read-model hooks while keeping the platform domain-neutral. CMS-specific identifiers, labels, and redaction rules remain in the CMS domain pack and consuming UI copy.

## Acceptance Criteria

- `SAFE-CMS-012A`: Analysts can see source identities linked to a canonical entity.
- `SAFE-CMS-012B`: Data stewards can review low-confidence merges and split incorrect identities.
- `SAFE-CMS-012C`: Graph analysts can inspect identity edges and confidence.
- `SAFE-CMS-012D`: Connector owners can map incoming identities through a shared resolution API.

## Task 1: Candidate Match Scoring Service

**Files:**
- Create: `backend/analytics/identity_resolution/models.py`
- Create: `backend/analytics/identity_resolution/service.py`
- Create: `backend/analytics/identity_resolution/__init__.py`
- Add focused service tests.

- [x] Represent canonical identity candidates, source references, match reasons, confidence, and review state with domain-neutral models.
- [x] Score candidate entities using configured natural keys and selected normalized identifier/address fields.
- [x] Require KB-scoped input and avoid cross-KB candidate leakage.
- [x] Return deterministic rankings with auditable match reasons.

**Notes:**
- Added `analytics.identity_resolution` with domain-neutral request/result models and a deterministic `IdentityResolutionService`.
- Candidate scoring uses configured field lists rather than CMS-specific property names.
- Natural key, identifier, and address matches emit auditable field-level reasons with bounded score contributions.
- Candidates outside the request KB are excluded and reported by ID instead of scored.
- RED:
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_service.py -q` failed with `ModuleNotFoundError: No module named 'analytics.identity_resolution'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_service.py -q`: 2 passed.
  - `uv run --project backend ruff check backend/analytics/identity_resolution backend/tests/analytics/test_identity_resolution_service.py`: passed.
  - `uv run --project backend pyright backend/analytics/identity_resolution backend/tests/analytics/test_identity_resolution_service.py`: 0 errors.

## Task 2: Graph Relationship Projection

**Files:**
- Extend identity service with relationship conversion helpers.
- Add graph-facing tests.

- [x] Emit relationship payloads that can be stored as normal `Relationship` objects.
- [x] Preserve confidence, decision source, and source identity metadata on each relationship.
- [x] Avoid hardcoded CMS relationship/entity names.

**Notes:**
- Added `IdentityRelationshipProjectionRequest` and `IdentityResolutionService.project_identity_relationships(...)`.
- Projection emits normal `Relationship` models from canonical candidate entity to source entity.
- Callers provide the domain-pack relationship type and decision source; no CMS relationship/entity names are hardcoded.
- Relationship properties carry confidence, score, review state, and decision source; metadata carries KB id, entity types, source refs, and field-level match reasons.
- RED:
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_service.py -q` failed with `ImportError: cannot import name 'IdentityRelationshipProjectionRequest'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_service.py -q`: 3 passed.
  - `uv run --project backend ruff check backend/analytics/identity_resolution backend/tests/analytics/test_identity_resolution_service.py`: passed.
  - `uv run --project backend pyright backend/analytics/identity_resolution backend/tests/analytics/test_identity_resolution_service.py`: 0 errors.

## Task 3: Persistence and Review Decisions

**Files:**
- Add repository protocols and in-memory/Postgres adapters.
- Add migrations/tests.

- [x] Persist identity links, source refs, review state, and decision history.
- [x] Support manual merge/split decisions.
- [x] Publish durable audit/event hooks for material decisions.

**Task 3a Notes:**
- Added `IdentityLinkRecord`, `IdentityLinkRepository` protocol, `InMemoryIdentityLinkRepository`, and `IdentityDecisionService`.
- In-memory persistence is KB scoped and defensive-copy safe.
- Steward decisions append decision history and transition links to `merged`, `rejected`, or `split`.
- Postgres persistence, migrations, and durable audit/event hooks remain open for the next Task 3 slice.
- RED:
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_repository.py -q` failed with `ImportError: cannot import name 'IdentityDecisionService'`.
- GREEN:
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_service.py backend/tests/analytics/test_identity_resolution_repository.py -q`: 5 passed.
  - `uv run --project backend ruff check backend/analytics/identity_resolution backend/tests/analytics/test_identity_resolution_service.py backend/tests/analytics/test_identity_resolution_repository.py`: passed.
  - `uv run --project backend pyright backend/analytics/identity_resolution backend/tests/analytics/test_identity_resolution_service.py backend/tests/analytics/test_identity_resolution_repository.py`: 0 errors.

**Task 3b Notes:**
- Added `PostgresIdentityLinkRepository` with KB-scoped get/list queries and JSONB-backed source refs, match reasons, and decision history.
- Added Alembic migration `0018_identity_links` plus refreshed `backend/database/migrations/snapshots/head.sql`.
- `IdentityDecisionService` now publishes `identity.link_decision.recorded` events and records audit ledger entries for material steward decisions.
- Review pass found and fixed four Task 3 gaps before API work: event codec registration, composite KB-scoped Postgres identity-link key/upsert, stricter all-items decision-history validation, and `tenant_id` non-empty validation.
- RED:
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_repository.py backend/tests/database/test_identity_links_migration.py backend/tests/analytics/test_identity_resolution_postgres.py`: initially failed because Postgres was not running after the system restart.
  - `uv run --project backend pytest backend/tests/events/test_codec.py::test_event_codec_round_trips_identity_link_decision_event backend/tests/analytics/test_identity_resolution_repository.py::test_identity_decision_request_rejects_empty_tenant_id`: failed with unsupported event type and missing tenant validation.
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_postgres.py::test_postgres_identity_link_repository_keeps_same_link_id_kb_scoped backend/tests/analytics/test_identity_resolution_postgres.py::test_identity_links_constraint_rejects_any_invalid_decision_history_item`: failed with cross-KB overwrite and permissive decision-history constraint.
- GREEN:
  - `docker compose -f docker-compose.dev.yaml up -d postgres`: Postgres healthy.
  - `uv run --project backend pytest backend/tests/analytics/test_identity_resolution_service.py backend/tests/analytics/test_identity_resolution_repository.py backend/tests/analytics/test_identity_resolution_postgres.py backend/tests/database/test_identity_links_migration.py backend/tests/events/test_codec.py`: 37 passed.
  - `uv run --project backend ruff check backend/analytics/identity_resolution backend/events/codec.py backend/events/types.py backend/tests/analytics/test_identity_resolution_repository.py backend/tests/analytics/test_identity_resolution_postgres.py backend/tests/database/test_identity_links_migration.py backend/tests/events/test_codec.py`: passed.
  - `uv run --project backend pyright backend/analytics/identity_resolution backend/events/codec.py backend/events/types.py backend/tests/analytics/test_identity_resolution_repository.py backend/tests/analytics/test_identity_resolution_postgres.py backend/tests/database/test_identity_links_migration.py backend/tests/events/test_codec.py`: 0 errors.
  - `scripts/ci_migration_check.sh --update-snapshot`: passed and regenerated `head.sql`.
  - `scripts/ci_migration_check.sh`: passed; migration replay clean and schema matched `head.sql`.

## Task 4: API Contract

**Files:**
- Add identity API contracts/router wiring/tests.

- [x] Expose canonical identity detail by KB/entity.
- [x] Expose candidate resolution for connector/ingestion callers.
- [x] Expose steward review actions with audit metadata.

**Notes:**
- Added `/identity/canonical/{entity_id}` for KB-scoped canonical identity links.
- Added `/identity/resolve-candidates` for connector/ingestion callers to score source identities against canonical candidates.
- Added `/identity/links/{link_id}/decision` to record steward merge/split decisions through the audited `IdentityDecisionService`.
- Refreshed `chili_app/openapi.json` and generated `chili_app/src/lib/api/schema.ts`.
- Review pass blocked Task 5 on two API issues; fixed KB-scoped authorization for every identity endpoint and now derive audit actor metadata from the authenticated user instead of the request body.
- RED:
  - `uv run --project backend pytest backend/tests/api/test_identity_router.py`: failed with missing `get_identity_link_repository` API dependency.
  - `uv run --project backend pytest backend/tests/api/test_identity_router.py backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_lists_all_required_paths backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_tags_cover_all_routers`: failed with unauthorized KB requests returning 200 and forged actor metadata being persisted.
- GREEN:
  - `uv run --project backend pytest backend/tests/api/test_identity_router.py`: 3 passed.
  - `uv run --project backend pytest backend/tests/api/test_identity_router.py backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_lists_all_required_paths backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_tags_cover_all_routers`: 8 passed.
  - `uv run --project backend pytest backend/tests/api/test_identity_router.py backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_lists_all_required_paths backend/tests/api/test_app.py::TestOpenApiSchema::test_openapi_tags_cover_all_routers backend/tests/api/test_app.py::TestRouterRegistration::test_analytics_router_is_registered`: 6 passed.
  - `uv run --project backend ruff check backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/api/routers/identity.py backend/tests/api/test_identity_router.py`: passed.
  - `uv run --project backend pyright backend/api/contracts.py backend/api/dependencies.py backend/api/app.py backend/api/routers/identity.py backend/tests/api/test_identity_router.py`: 0 errors.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api` in `chili_app`: passed.

## Task 5: Cockpit and Dossier Identity Panels

**Files:**
- Add frontend API client, components, and page integration tests.

- [x] Show aliases/source refs, confidence, review state, and decision history.
- [x] Preserve dense cockpit layout and mobile constraints.
- [x] Hide or redact configured sensitive fields.

**Notes:**
- Added `chili_app/src/api/identity.ts` with KB/entity-scoped canonical identity detail fetching and React Query keys.
- Added `IdentityPanel` for compact dossier rendering of linked source identities, confidence meters, review state, match reasons, source refs, and decision history.
- Wired the panel into `InvestigationWorkbenchPage` for the selected KB/entity and added page-level regression coverage.
- Source references matching sensitive identifier tokens are masked as `Restricted ref` while non-sensitive refs remain visible.
- Review gate approved Task 5 with no findings; aliases are represented by the current API's source entity IDs and source refs.
- RED:
  - `npm run test:run -- src/api/__tests__/identity.test.ts src/components/investigation/__tests__/IdentityPanel.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: failed with missing `api/identity`, missing `IdentityPanel`, and no Identity resolution panel on the workbench.
- GREEN:
  - `npm run test:run -- src/api/__tests__/identity.test.ts src/components/investigation/__tests__/IdentityPanel.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: 43 passed.
  - `npx eslint src/api/identity.ts src/api/__tests__/identity.test.ts src/components/investigation/IdentityPanel.tsx src/components/investigation/__tests__/IdentityPanel.test.tsx src/pages/InvestigationWorkbenchPage.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/api/contracts.ts`: passed.
  - `pnpm build` in `chili_app`: passed with the existing bundle-size warning.
  - `git diff --check`: passed.

## Review Gates

- Review after Task 1 before adding graph projection or persistence.
- Review after Task 3 before API/UI work.
- Review after Task 5 before backlog closeout.

## Definition Of Done

- Focused backend unit tests prove deterministic scoring, KB scoping, and low-confidence handling.
- Persistence/API/UI slices have focused tests before each implementation.
- Backlog is updated only when the sprint acceptance criteria are fully implemented.
