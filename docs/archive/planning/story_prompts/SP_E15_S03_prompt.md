# Story E15-S03: GraphContextExpander — configurable depth, entity type filters, and timeout

## Story
As a platform developer, I want the `GraphContextExpanderProtocol` to support configurable expansion depth, entity type filtering, and a deadline timeout so expensive graph traversals can be bounded in production.

## Acceptance Criteria
1. `rag/adapters/protocols.py` extends `GraphContextExpanderProtocol.expand()` with: `depth: int = 1`, `entity_type_filter: list[str] | None = None`, `timeout_ms: int | None = None`.
2. The call signature remains backward-compatible.
3. The in-memory `GraphContextExpander` stub respects `entity_type_filter` (filters returned nodes by type) and ignores `depth` (stubs return flat neighbors) and `timeout_ms`.
4. Unit tests cover: type filter applied, no filter returns all types, depth=2 accepted without error on stub.

## Priority / Size / Dependencies
| Priority | Size | Dependencies |
|----------|------|--------------|
| P1       | S    | None         |

## Target Files
- `backend/rag/adapters/protocols.py` — extend `GraphContextExpanderProtocol.expand()` signature
- `backend/rag/adapters/in_memory.py` — update in-memory stub to respect `entity_type_filter`
- `backend/tests/rag/test_adapters.py` — add tests for extended expander

## Reference Files to Read First
- `backend/rag/adapters/protocols.py` — current `GraphContextExpanderProtocol`
- `backend/rag/adapters/in_memory.py` — in-memory stub
- `backend/rag/models.py` — `GraphContext`, `RetrievedContextItem`
- `backend/tests/rag/` — existing RAG tests

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- Backward compatibility is mandatory
- `timeout_ms` enforcement in production adapters is their responsibility; the protocol declares the parameter only
- `depth` must be `>= 1`; validate with `Field(ge=1)` or an assertion in the stub

## What NOT To Do
- Do not implement the Neo4j-backed expander here — that is E6-S03
- Do not add streaming interface here — separate story
- Do not change `GraphContext` model structure; expand response shape only if needed for filter results

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=rag tests/rag/` >= 85% coverage
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
