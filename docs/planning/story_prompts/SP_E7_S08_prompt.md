# Story E7-S08: Explainability — Structured Narrative Generation

## Story
As a platform developer, I want the explainability service to produce structured multi-section narratives.

## Acceptance Criteria
1. `ExplainabilityResponse` gains `narrative: ExplanationNarrative` with `summary`, `sections: list[NarrativeSection]`.
2. `NarrativeSection`: `heading`, `body`, `evidence_refs: list[str]`.
3. `_build_reasoning()` refactored to produce structured narrative, grouping by `source_type`.
4. `evidence_pack.reasoning` populated with flattened `summary` for backward compat.
5. Tests verify section grouping and backward-compatible `reasoning`.

## Priority / Size / Dependencies

| Field        | Value |
|--------------|-------|
| Priority     | P2    |
| Size         | M     |
| Dependencies | None  |

## Target Files
- `backend/analytics/explainability/models.py` — add `ExplanationNarrative` and `NarrativeSection` domain models
- `backend/analytics/explainability/service_models.py` — add `narrative: ExplanationNarrative` to `ExplainabilityResponse`
- `backend/analytics/explainability/service.py` — refactor `_build_reasoning()` to produce structured narrative grouped by `source_type`
- `backend/tests/analytics/explainability/test_service.py` — add tests for section grouping, evidence refs, and backward-compatible `reasoning`

## Reference Files to Read First
- `backend/analytics/explainability/service.py` — current service implementation with `_build_reasoning()`
- `backend/analytics/explainability/service_models.py` — current response models
- `backend/analytics/explainability/models.py` — current domain models (ExplanationItem, source_type, etc.)
- `backend/analytics/explainability/protocols.py` — service protocol definition
- `backend/analytics/explainability/exceptions.py` — existing exception types
- `backend/tests/analytics/explainability/test_service.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `ExplanationNarrative` and `NarrativeSection` are domain models in `models.py`
- Sections are grouped by `source_type` of the underlying `ExplanationItem`s
- `evidence_refs` in each section should reference the item IDs contributing to that section
- `evidence_pack.reasoning` must still be populated with the flattened summary string for backward compatibility
- Narrative generation is deterministic — same input items produce same sections in same order

## What NOT To Do
- Do NOT remove or break the existing `evidence_pack.reasoning` field
- Do NOT import from other analytics sub-modules (timeseries, gnn, risk)
- Do NOT add API endpoints — this is service-layer only
- Do NOT use an LLM to generate narrative text — this is rule-based structured grouping
- Do NOT change the `ExplainabilityContextSourceProtocol` interface

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/explainability tests/analytics/explainability/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
