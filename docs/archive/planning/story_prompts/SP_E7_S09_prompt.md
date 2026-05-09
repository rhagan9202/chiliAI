# Story E7-S09: Explainability — SHAP/LIME Feature Attribution Adapter

## Story
As a platform developer, I want an explainability adapter using SHAP/LIME for feature attribution.

## Acceptance Criteria
1. `analytics/explainability/adapters/shap_adapter.py` implements `ExplainabilityContextSourceProtocol`.
2. Accepts trained model + input features, computes SHAP values, maps to `ExplanationItem`.
3. Test with minimal sklearn model verifies SHAP computation and mapping.
4. Optional — guarded import.

## Priority / Size / Dependencies

| Field        | Value  |
|--------------|--------|
| Priority     | P3     |
| Size         | L      |
| Dependencies | E7-S06 |

## Target Files
- `backend/analytics/explainability/adapters/shap_adapter.py` — new adapter implementing `ExplainabilityContextSourceProtocol` using SHAP
- `backend/tests/analytics/explainability/test_shap_adapter.py` — tests with minimal sklearn model
- `backend/pyproject.toml` — add `shap` to optional `[analytics]` dependency group

## Reference Files to Read First
- `backend/analytics/explainability/protocols.py` — `ExplainabilityContextSourceProtocol` definition
- `backend/analytics/explainability/models.py` — `ExplanationItem` and related domain types
- `backend/analytics/explainability/service_models.py` — request/response models
- `backend/analytics/explainability/adapters/` — existing adapter implementations for pattern reference
- `backend/analytics/explainability/service.py` — how context sources are consumed
- `backend/tests/analytics/explainability/` — existing test patterns
- `backend/pyproject.toml` — current optional dependency groups

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `shap` must be an optional dependency under `[analytics]` extra — guard import with `try/except ImportError`
- Adapter must implement `ExplainabilityContextSourceProtocol` exactly — no extra public methods
- SHAP values must be mapped to `ExplanationItem` instances with proper `source_type`, `description`, and `weight`
- Test must use a minimal `sklearn` model (e.g., `DecisionTreeClassifier` on synthetic data) to keep tests fast
- If `shap` is not installed, adapter construction should raise a clear `ImportError` with install instructions

## What NOT To Do
- Do NOT make `shap` a required (non-optional) dependency
- Do NOT modify the `ExplainabilityContextSourceProtocol` interface
- Do NOT import from other analytics sub-modules (timeseries, gnn, risk)
- Do NOT add API endpoints — this is adapter-layer only
- Do NOT implement LIME in this story — SHAP only (LIME can be a future adapter)
- Do NOT train complex models in tests — use minimal synthetic data

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=analytics/explainability tests/analytics/explainability/` >= 85% coverage
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `ShapExplainabilityContextSource` lazily
imports `shap`, raising `ExplainabilityConfigurationError` when missing.
The adapter resolves a SHAP-callable target (`predict_proba` preferred,
falling back to `predict`), accepts an optional `background` masker, and
maps SHAP attributions into `ExplanationItem` instances with normalized
absolute scores. `shap>=0.43` was added to the `[analytics]` extra.

## Validation Note
From `backend/`: `.venv/bin/pytest
tests/analytics/explainability/test_shap_adapter.py` skips cleanly when
`shap` / `scikit-learn` are absent and runs 12 tests when installed.
With shap installed, `shap_adapter.py` covers 94% of statements; the
broader `analytics/explainability` package is at 96%.
