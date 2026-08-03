# SAFE-CMS-004 Evidence Provenance Implementation Plan

**Owner:** Codex
**Date:** 2026-08-03
**Branch:** `fix/normalize-kb-query-param`
**Parent dependencies:** `SAFE-CMS-001`, `SAFE-CMS-002`, `SAFE-CMS-003` through commit `f194d5b`

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> for implementation slices and `superpowers:test-driven-development` for behavior changes.

## Goal

Persist normalized provenance for scores, alerts, evidence packs, citations, narratives,
graph context, source records, model versions, prompts, and workflow runs while preserving
legacy evidence packs and keeping full citation navigation for SAFE-CMS-007.

## Current Inventory

- `shared.types.EvidencePack` is the object-store serialized evidence bundle.
- Existing evidence responses include scores, source documents, attribution, and narrative
  sections, but no normalized provenance references.
- `ObjectStoreEvidencePackRepository` serializes `EvidencePack.model_dump_json()` and reads
  with `EvidencePack.model_validate_json()`, so model defaults are the first compatibility gate.
- `_evidence_pack_to_response` in `backend/api/dependencies.py` maps persisted packs to
  `EvidencePackResponse`.
- `ExplainabilityService.generate_from_context` creates evidence packs from explanation items,
  subgraph ids, scores, attribution, and narrative sections.

## Task 1: Shared Provenance Model And API Serialization

**Files:**
- Modify: `backend/shared/types.py`
- Modify: `backend/api/contracts.py`
- Modify: `backend/api/dependencies.py`
- Test: `backend/tests/shared/test_types.py`
- Test: `backend/tests/api/test_read_model_routers.py`

- [x] **Step 1: Write failing backward-compatibility and API mapper tests**

Cover legacy evidence packs defaulting to empty provenance, round-trip of structured
provenance references through `EvidencePack.model_dump()` / `model_validate()`, and
`GET /evidence-packs/{id}` returning provenance.

- [x] **Step 2: Add normalized provenance reference models**

Add a shared `EvidenceProvenanceReference` with at least `reference_type`,
`reference_id`, `label`, `source_system`, `source_version`, `transformation_version`,
`confidence`, `route_target`, and `metadata`. Add `provenance: list[...]` to
`EvidencePack` with a default empty list.

- [x] **Step 3: Add API response contracts and mapper support**

Expose provenance in `EvidencePackResponse` using response models that preserve the
same field names. Existing packs must continue to return `provenance: []`.

- [x] **Step 4: Focused verification**

Run shared type tests, evidence read-model route tests, compileall for shared/API paths,
OpenAPI export if contracts changed, and `git diff --check`.

Task 1 notes:

- Added `EvidenceProvenanceReference` and `EvidencePack.provenance` with default empty
  provenance for legacy packs and JSON-safe metadata validation.
- Added `EvidenceProvenanceReferenceResponse` and mapped persisted refs through
  `EvidencePackResponse`.
- Added focused mapper coverage in `backend/tests/api/test_evidence_payloads.py` because the
  existing app-level evidence route test prints passing dots but hangs in this checkout's
  TestClient teardown.
- Verification passed:
  - `backend/tests/shared/test_types.py backend/tests/api/test_evidence_payloads.py -q`: 64 passed.
  - `compileall backend/shared backend/api`: passed.
  - `git diff --check`: passed.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.

## Task 2: Provenance Persistence And Repository Query Seam

**Files:**
- Create/modify: provenance repository/service under `analytics/explainability`
- Create: migration for queryable provenance rows if object-store fields are insufficient
- Test: repository and migration tests

- [x] Add a repository protocol for KB/evidence-pack scoped provenance references.
- [x] Implement durable storage or a documented object-store-backed first slice.
- [x] Ensure KB deletion purges provenance rows or embedded pack refs.

Task 2 notes:

- Added `analytics.explainability.provenance.EvidenceProvenanceRepository` and
  `EvidencePackProvenanceRepository`, backed by the durable evidence-pack repository.
- Added `EvidenceProvenanceListResponse`, a pure response builder, DI wiring, the existing
  `/evidence-packs/{evidence_pack_id}/provenance` route, and the PI-spec route
  `/knowledgebases/{knowledge_base_id}/evidence-packs/{evidence_pack_id}/provenance`.
- Kept the provenance dependency as a lightweight per-request wrapper around the current
  evidence-pack repository so app-state swaps cannot retain stale repository instances.
- No new SQL migration was added in this slice: provenance is persisted inside the existing
  object-store evidence-pack artifact, and KB deletion already purges embedded provenance by
  deleting evidence packs. A later adapter can replace the seam with normalized SQL rows if
  high-volume querying requires it.
- Verification passed:
  - `backend/tests/analytics/explainability/test_evidence_repository.py backend/tests/analytics/explainability/test_evidence_provenance_repository.py backend/tests/api/test_evidence_payloads.py -q`: 14 passed.
  - `compileall backend/analytics/explainability backend/api`: passed.
  - `git diff --check`: passed.
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.

## Task 3: Generation-Time Provenance Enrichment

**Files:**
- Modify: `backend/analytics/explainability/service.py`
- Modify: coordinator explainability flow as needed
- Test: evidence service tests

- [x] Add provenance references for explanation items, subgraph nodes/edges, score snapshots,
  feature attribution, model/prompt versions where available, and workflow/correlation ids.
- [x] Preserve deterministic behavior for tests and local generation.

Task 3 notes:

- Added optional `ExplanationLineage` to generation contexts and wired Flow B correlation IDs
  plus deterministic risk request IDs into generated evidence packs.
- Added generation-time provenance refs for selected explanation items, graph nodes/edges,
  score snapshots, feature attributions, narrative sections, correlation IDs, workflow IDs,
  and model/prompt versions when provided by context or the narrative generator.
- Review fixes: same-document explanation items now keep distinct provenance refs; document
  route targets point to the viewer-safe preview route; provenance metadata stores bounded
  snippets/lengths instead of unbounded generated prose; `LlmNarrativeGenerator` exposes its
  configured model and prompt contract version for lineage.
- Verification passed:
  - Red tests first failed on missing `ExplanationLineage` / `correlation_id` context support.
  - `backend/tests/analytics/explainability backend/tests/agent/test_explainability_stage.py -q`: 65 passed.
  - `ruff check` on touched backend files: passed.
  - `uv run --project backend pyright` on touched backend files: passed.
  - `compileall backend/analytics/explainability backend/agent`: passed.
  - `git diff --check`: passed.

## Task 4: Frontend Provenance Rendering

**Files:**
- Regenerate OpenAPI/frontend types.
- Modify evidence components/pages under `chili_app/src`.
- Test focused component/API hook tests and build.

- [x] Add provenance badges and expandable metadata to existing evidence panels.
- [x] Keep navigation targets inert or best-effort until SAFE-CMS-007 route resolution.

Task 4 notes:

- Added provenance rendering to `EvidencePackViewer`: compact reference-type badges, per-ref
  expandable detail rows, confidence/source/version metadata, and bounded metadata previews.
- Kept `route_target` inert as displayed provenance data instead of live SPA links; SAFE-CMS-007
  can translate route targets into navigable app destinations later.
- Review fixes: details are collapsed by default, arbitrary metadata rows and values are capped
  with a hidden-count indicator, route targets are not anchors, and long IDs/targets wrap in the panel.
- Verification passed:
  - Red viewer test first failed on missing provenance rendering.
  - `pnpm test:run src/components/investigation/__tests__/EvidencePackViewer.test.tsx`: 6 passed.
  - `pnpm test:run src/components/investigation/__tests__/EvidencePackViewer.test.tsx src/components/investigation/__tests__/EvidencePackActions.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`: 71 passed.
  - `pnpm exec eslint` on touched frontend component/test files: passed.
  - `npm run codegen:api`: passed with no generated diff.
  - `pnpm build`: passed with the existing Vite large-chunk warning.

## Review Gates

- Review after Task 1 before adding durable provenance storage.
- Review after Task 3 before frontend work.
- Final review before commit/push.

## Open Questions

- Whether queryable provenance needs its own SQL table in Sprint 4 or can begin as embedded
  evidence-pack refs plus a later extracted table.
- Which model/prompt version fields are currently available from LLM adapters versus needing
  new generation metadata.
- How much route-target structure belongs in SAFE-CMS-004 versus SAFE-CMS-007 citation navigation.
