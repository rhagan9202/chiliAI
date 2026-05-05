# Story E20-S02: Explainability adapter protocol — batch loading and rich context queries

## Story
As a platform developer, I want the `ExplainabilityAdapterProtocol` to expose batch explanation loading and richer context query methods so production adapters can efficiently serve explanation panels in the Investigation Workbench.

## Acceptance Criteria
1. `analytics/explainability/adapters/protocols.py` adds to `ExplainabilityAdapterProtocol`:
   - `batch_explain(requests: list[ExplainabilityRequest]) -> list[ExplainabilityResult]`
   - `get_context(entity_id: str, kb_id: str) -> ExplainabilityContext` — returns evidence metadata, relevant feature names, and top contributing entities for a given entity
2. `analytics/explainability/models.py` adds `ExplainabilityContext(entity_id, kb_id, feature_contributions: dict[str, float], top_entities: list[str], evidence_summary: str | None)`.
3. The in-memory/baseline adapter implements `batch_explain` as a loop and `get_context` returning an empty/stub `ExplainabilityContext`.
4. Unit tests cover: batch of two, `get_context` returns correct shape, empty batch returns empty list.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | S    | None         |

## Target Files
- `backend/analytics/explainability/adapters/protocols.py` — add `batch_explain`, `get_context`
- `backend/analytics/explainability/models.py` — add `ExplainabilityContext`
- `backend/analytics/explainability/adapters/in_memory.py` — implement new methods
- `backend/tests/analytics/explainability/test_adapter.py` — add tests

## Reference Files to Read First
- `backend/analytics/explainability/adapters/protocols.py` — current protocol
- `backend/analytics/explainability/models.py` — existing models
- `backend/analytics/explainability/adapters/in_memory.py` — current adapter
- `backend/tests/analytics/explainability/` — existing tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `ExplainabilityContext.feature_contributions` maps feature name → impact score in `[0, 1]`
- `batch_explain` returns results in input order
- `get_context` must not raise on unknown entity — return a stub context with empty contributions

## What NOT To Do
- Do not implement SHAP/LIME here — those are E7-S09
- Do not add streaming interface in this story
- Do not change the `ExplainabilityRequest` or `ExplainabilityResult` models

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/explainability tests/analytics/explainability/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
