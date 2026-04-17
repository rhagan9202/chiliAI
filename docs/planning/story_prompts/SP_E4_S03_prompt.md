# Story E4-S03: Emit kb.ready event at pipeline completion

## Story
As a platform developer, I want the worker to emit a `kb.ready` event after `vectors.indexed`.

## Acceptance Criteria
1. `agent/coordinator.py` registers a handler for `VectorsIndexedEvent`.
2. The handler publishes a `KnowledgeBaseReadyEvent` containing `knowledge_base_id`, total entity count, relationship count, and vector count.
3. `events/types.py` defines `KnowledgeBaseReadyEvent`.
4. If a KnowledgeBase record store is available, the handler updates KB status to `"ready"`.
5. Unit test verifies the full pipeline chain from `documents.uploaded` through `kb.ready`.

## Priority / Size / Dependencies
| Field        | Value          |
|--------------|----------------|
| Priority     | P1             |
| Size         | S              |
| Dependencies | E4-S02, E1-S09 |

## Target Files
- `backend/agent/coordinator.py` — add `VectorsIndexedEvent` handler, KB ready emission
- `backend/events/types.py` — define `KnowledgeBaseReadyEvent`
- `backend/tests/agent/test_coordinator.py` — unit tests for the handler and full pipeline chain test

## Reference Files to Read First
- `backend/agent/coordinator.py` — current coordinator structure and all existing pipeline handlers
- `backend/events/types.py` — existing event types including `VectorsIndexedEvent`
- `backend/events/protocols.py` — `EventBus` protocol
- `backend/agent/models.py` — agent/KB models for status tracking
- `backend/storage/protocols.py` — object storage protocol
- `backend/tests/agent/test_coordinator.py` — existing test patterns

## Architectural Constraints
- Python 3.12, compatible with `pyright --strict`
- All public APIs fully type-annotated
- No cross-module imports except via `shared/`, FastAPI gateway orchestration, or agent coordinator
- Follow existing patterns in the codebase
- `KnowledgeBaseReadyEvent` must include all summary counts: entity count, relationship count, vector count
- The handler should gracefully handle the case where no KB record store is available (skip status update, still emit event)
- `correlation_id` must be propagated from the incoming event
- The full pipeline chain test should exercise: `documents.uploaded` → `ingestion.complete` → `graph.updated` → `embeddings.complete` → `vectors.indexed` → `kb.ready`

## What NOT To Do
- Do not introduce new storage or DB abstractions for KB status — use what exists or skip gracefully
- Do not make the KB record store a hard dependency; it must be optional
- Do not add REST endpoints — this is worker-only logic
- Do not fabricate count values; derive them from pipeline context or event payloads
- Do not break existing pipeline handler registrations

## Done Checklist
- [ ] All acceptance criteria met
- [ ] All target files created/modified
- [ ] Tests written and passing
- [ ] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [ ] No lint errors (`ruff check`)
- [ ] Type-safe (`pyright --strict` compatible)
