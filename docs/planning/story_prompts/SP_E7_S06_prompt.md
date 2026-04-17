# Story E7-S06: Risk Scoring — Ensemble Model with Configurable Strategies

## Story
As a platform developer, I want the risk service to support pluggable scoring strategies behind a `RiskScoringStrategy` protocol.

## Acceptance Criteria
1. `analytics/risk/protocols.py` defines `RiskScoringStrategyProtocol` with `score(signals) -> list[RiskFactor]`.
2. Existing linear weighted-sum extracted into `LinearScoringStrategy`.
3. `RiskService` accepts `scoring_strategy` dependency.
4. Tests verify delegation and identical results to current implementation.

## Priority / Size / Dependencies

| Field        | Value |
|--------------|-------|
| Priority     | P1    |
| Size         | M     |
| Dependencies | None  |

## Target Files
- `backend/analytics/risk/protocols.py` — add `RiskScoringStrategyProtocol` with `score()` method
- `backend/analytics/risk/service.py` — refactor to accept `scoring_strategy` dependency; delegate scoring through protocol
- `backend/analytics/risk/adapters/` — create `linear_strategy.py` with `LinearScoringStrategy` extracted from current inline logic
- `backend/analytics/risk/service_models.py` — adjust if service constructor changes affect request/response models
- `backend/tests/analytics/risk/test_service.py` — add tests verifying delegation and result parity with pre-refactor behavior
- `backend/tests/analytics/risk/test_linear_strategy.py` — unit tests for `LinearScoringStrategy` in isolation

## Reference Files to Read First
- `backend/analytics/risk/service.py` — current risk service with inline scoring logic to extract
- `backend/analytics/risk/protocols.py` — existing protocol definitions
- `backend/analytics/risk/models.py` — domain models (`RiskFactor`, etc.)
- `backend/analytics/risk/service_models.py` — request/response models
- `backend/analytics/risk/exceptions.py` — existing exception types
- `backend/analytics/risk/adapters/` — existing adapter implementations
- `backend/tests/analytics/risk/test_service.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `RiskScoringStrategyProtocol` must be a `typing.Protocol` (structural subtyping), not an ABC
- `LinearScoringStrategy` must produce byte-identical results to the current inline implementation
- `RiskService` must accept `scoring_strategy` via constructor injection (not method parameter)
- Default behavior when no strategy is provided: use `LinearScoringStrategy` (backward-compatible)

## What NOT To Do
- Do NOT change the external behavior of `RiskService.assess()` — outputs must remain identical
- Do NOT remove or rename existing public types (`RiskFactor`, response models, etc.)
- Do NOT import from other analytics sub-modules (timeseries, gnn, explainability)
- Do NOT add API endpoints — this is service-layer only
- Do NOT create an abstract base class — use Protocol for structural typing

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/risk tests/analytics/risk/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
