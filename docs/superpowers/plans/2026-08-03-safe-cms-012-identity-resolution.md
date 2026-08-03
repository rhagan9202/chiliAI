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

- [ ] Persist identity links, source refs, review state, and decision history.
- [ ] Support manual merge/split decisions.
- [ ] Publish durable audit/event hooks for material decisions.

## Task 4: API Contract

**Files:**
- Add identity API contracts/router wiring/tests.

- [ ] Expose canonical identity detail by KB/entity.
- [ ] Expose candidate resolution for connector/ingestion callers.
- [ ] Expose steward review actions with audit metadata.

## Task 5: Cockpit and Dossier Identity Panels

**Files:**
- Add frontend API client, components, and page integration tests.

- [ ] Show aliases/source refs, confidence, review state, and decision history.
- [ ] Preserve dense cockpit layout and mobile constraints.
- [ ] Hide or redact configured sensitive fields.

## Review Gates

- Review after Task 1 before adding graph projection or persistence.
- Review after Task 3 before API/UI work.
- Review after Task 5 before backlog closeout.

## Definition Of Done

- Focused backend unit tests prove deterministic scoring, KB scoping, and low-confidence handling.
- Persistence/API/UI slices have focused tests before each implementation.
- Backlog is updated only when the sprint acceptance criteria are fully implemented.
