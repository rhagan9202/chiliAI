# Story E20-S04: Risk adapter protocol — batch score loading and real-time signal streaming

## Story
As a platform developer, I want the `RiskAdapterProtocol` to support batch score loading for multiple entities at once and a real-time signal streaming interface so dashboards can display live risk updates and bulk scoring is efficient.

## Acceptance Criteria
1. `analytics/risk/adapters/protocols.py` adds to `RiskAdapterProtocol`:
   - `batch_load_signals(kb_id: str, entity_ids: list[str]) -> dict[str, list[RiskSignal]]` — returns a mapping of entity_id → signal list
   - `stream_signals(kb_id: str, entity_id: str) -> Iterator[RiskSignal]` — yields risk signals as they are produced (stub: yields all in-memory signals then stops)
2. The in-memory adapter implements both methods.
3. Unit tests cover: batch load returns correct mapping, unknown entity_id maps to empty list, stream_signals yields expected signals.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P2       | S    | None         |

## Target Files
- `backend/analytics/risk/adapters/protocols.py` — add `batch_load_signals`, `stream_signals`
- `backend/analytics/risk/adapters/in_memory.py` — implement new methods
- `backend/tests/analytics/risk/test_adapter.py` — add batch and streaming tests

## Reference Files to Read First
- `backend/analytics/risk/adapters/protocols.py` — current protocol
- `backend/analytics/risk/models.py` — `RiskSignal` and related models
- `backend/analytics/risk/adapters/in_memory.py` — current in-memory adapter
- `backend/tests/analytics/risk/` — existing risk tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- `batch_load_signals` must return an entry for every requested `entity_id`, even if empty
- `stream_signals` returns a synchronous `Iterator[RiskSignal]` — not async in this story
- The in-memory `stream_signals` is allowed to exhaust and stop (not an infinite stream)

## What NOT To Do
- Do not implement production risk streaming (WebSocket/SSE) here — that is E5-S07
- Do not add async variants in this story
- Do not change `RiskSignal` model fields

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=analytics/risk tests/analytics/risk/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
