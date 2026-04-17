# Story E7-S02: Timeseries — Isolation Forest Anomaly Detection

## Story
As a platform developer, I want the timeseries service to support isolation forest anomaly detection.

## Acceptance Criteria
1. New `detection_strategy: Literal[..., "isolation_forest"]` option added to the existing strategy literal.
2. New `_detect_anomalies_isolation_forest()` trains single-feature isolation forest.
3. Tests verify detection on synthetic data with planted outliers.
4. Contamination parameter configurable (default 0.05).

## Priority / Size / Dependencies

| Field        | Value |
|--------------|-------|
| Priority     | P2    |
| Size         | M     |
| Dependencies | None  |

## Target Files
- `backend/analytics/timeseries/service_models.py` — extend `detection_strategy` literal to include `"isolation_forest"`, add `contamination: float` field
- `backend/analytics/timeseries/service.py` — add `_detect_anomalies_isolation_forest()` method and routing logic
- `backend/tests/analytics/timeseries/test_service.py` — add tests for isolation forest strategy with synthetic outlier data
- `backend/pyproject.toml` — add `scikit-learn` to optional `[analytics]` dependency group

## Reference Files to Read First
- `backend/analytics/timeseries/service.py` — current service implementation and detection routing
- `backend/analytics/timeseries/service_models.py` — current request/response models (including any `detection_strategy` field from E7-S01)
- `backend/analytics/timeseries/models.py` — domain models
- `backend/analytics/timeseries/protocols.py` — service protocol definition
- `backend/analytics/timeseries/exceptions.py` — existing exception types
- `backend/tests/analytics/timeseries/test_service.py` — existing test patterns
- `backend/pyproject.toml` — current dependency configuration

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Use `sklearn.ensemble.IsolationForest` for anomaly detection
- `scikit-learn` added as optional dependency under `[analytics]` extra — guard import with `try/except ImportError`
- Contamination parameter must be validated (0.0 < contamination <= 0.5)
- Extend the existing `Literal` type for `detection_strategy` — do not replace it

## What NOT To Do
- Do NOT remove or modify existing z-score or STL detection logic
- Do NOT make `scikit-learn` a required (non-optional) dependency
- Do NOT change the return type or signature of existing public methods in a breaking way
- Do NOT import from other analytics sub-modules (gnn, risk, explainability)
- Do NOT add API endpoints — this is service-layer only
- Do NOT use multi-feature isolation forest — single-feature only per the AC

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/timeseries tests/analytics/timeseries/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
