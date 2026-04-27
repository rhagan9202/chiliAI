# Story E7-S07: Risk Scoring — Temporal Trend Comparison

## Story
As a platform developer, I want the risk service to compare current assessment score to historical baseline.

## Acceptance Criteria
1. `RiskAssessmentResponse` gains `trend: Literal["increasing", "stable", "decreasing"] | None` and `previous_score: float | None`.
2. `RiskSignalSourceProtocol` gains `load_historical_score(kb_id, entity_id) -> float | None`.
3. `RiskService.assess()` fetches historical score and computes trend (delta threshold default 0.05).
4. `InMemoryRiskSignalSource` returns `None` by default.
5. Tests verify each trend outcome.

## Priority / Size / Dependencies

| Field        | Value  |
|--------------|--------|
| Priority     | P2     |
| Size         | S      |
| Dependencies | E7-S06 |

## Target Files
- `backend/analytics/risk/service_models.py` — add `trend` and `previous_score` fields to `RiskAssessmentResponse`
- `backend/analytics/risk/protocols.py` — add `load_historical_score(kb_id, entity_id) -> float | None` to `RiskSignalSourceProtocol`
- `backend/analytics/risk/service.py` — add trend computation logic in `assess()`
- `backend/analytics/risk/adapters/in_memory.py` — implement `load_historical_score()` returning `None` by default
- `backend/tests/analytics/risk/test_service.py` — add tests for increasing, stable, decreasing, and None (no history) trend outcomes

## Reference Files to Read First
- `backend/analytics/risk/service.py` — current risk service (post E7-S06 refactor with scoring strategy)
- `backend/analytics/risk/service_models.py` — current response models
- `backend/analytics/risk/protocols.py` — current protocols (including `RiskScoringStrategyProtocol` from E7-S06)
- `backend/analytics/risk/adapters/in_memory.py` — existing in-memory adapter
- `backend/tests/analytics/risk/test_service.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- Trend is a `Literal["increasing", "stable", "decreasing"] | None` — `None` when no historical score exists
- Delta threshold of 0.05 should be a configurable parameter with default, not a magic constant
- Trend computation: `increasing` if current - previous > threshold, `decreasing` if previous - current > threshold, `stable` otherwise
- `load_historical_score` is part of the signal source protocol, not a separate dependency

## What NOT To Do
- Do NOT change the scoring strategy logic from E7-S06
- Do NOT import from other analytics sub-modules (timeseries, gnn, explainability)
- Do NOT add API endpoints — this is service-layer only
- Do NOT store historical scores in this story — only read them via the protocol
- Do NOT make trend computation block or fail if historical score is unavailable

## Done Checklist
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=analytics/risk tests/analytics/risk/` >= 85% coverage
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `RiskAssessmentResponse` gained
`previous_score: float | None` and a `Literal` `trend` of `increasing` /
`stable` / `decreasing` / `None`. `RiskSignalSourceProtocol` exposes
`load_historical_score`; `InMemoryRiskSignalSource` defaults to `None` and
honors a fixture-injected mapping. `RiskService.assess()` compares against
the configurable `DEFAULT_TREND_DELTA_THRESHOLD` (0.05) without blocking if
the historical lookup raises.

## Validation Note
From `backend/`: `.venv/bin/pytest tests/analytics/risk/` covers all four
trend branches (including the no-history `None` case); sub-module coverage
96%.
