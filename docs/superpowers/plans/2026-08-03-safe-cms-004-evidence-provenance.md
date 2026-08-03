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
  - `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json`: passed.
  - `npm run codegen:api`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.

## Task 2: Provenance Persistence And Repository Query Seam

**Files:**
- Create/modify: provenance repository/service under `analytics/explainability`
- Create: migration for queryable provenance rows if object-store fields are insufficient
- Test: repository and migration tests

- [ ] Add a repository protocol for KB/evidence-pack scoped provenance references.
- [ ] Implement durable storage or a documented object-store-backed first slice.
- [ ] Ensure KB deletion purges provenance rows or embedded pack refs.

## Task 3: Generation-Time Provenance Enrichment

**Files:**
- Modify: `backend/analytics/explainability/service.py`
- Modify: coordinator explainability flow as needed
- Test: evidence service tests

- [ ] Add provenance references for explanation items, subgraph nodes/edges, score snapshots,
  feature attribution, model/prompt versions where available, and workflow/correlation ids.
- [ ] Preserve deterministic behavior for tests and local generation.

## Task 4: Frontend Provenance Rendering

**Files:**
- Regenerate OpenAPI/frontend types.
- Modify evidence components/pages under `chili_app/src`.
- Test focused component/API hook tests and build.

- [ ] Add provenance badges and expandable metadata to existing evidence panels.
- [ ] Keep navigation targets inert or best-effort until SAFE-CMS-007 route resolution.

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
