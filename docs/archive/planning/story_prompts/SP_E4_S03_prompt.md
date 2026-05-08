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
- [x] All acceptance criteria met
- [x] All target files created/modified
- [x] Tests written and passing
- [x] `pytest --cov=agent tests/agent/` >= 85% coverage for affected module
- [x] No lint errors (`ruff check`)
- [x] Type-safe (`pyright --strict` compatible)

## Implementation Note
Completed on April 26, 2026. `handle_vectors_indexed` is now wired in
`handle_event` for `VectorsIndexedEvent`. The handler groups vector totals
per `knowledge_base_id`, queries the injected `GraphRepository` for entity
and relationship counts (gracefully tolerating `count_*` failures so the
pipeline does not stall when graph counts are unavailable), and publishes a
new `KnowledgeBaseReadyEvent` (event type `kb.ready`) carrying
`KnowledgeBaseReadyReference` records with `entity_count`,
`relationship_count`, and `vector_count`. `correlation_id` is propagated
from the incoming event. The codec registry was extended so the Redis
adapter serializes `kb.ready` end-to-end. A test exercises the full chain
from `documents.uploaded` through `kb.ready` by seeding graph and
validation artifacts and draining the in-memory bus repeatedly.

## Validation Note
From `backend/`: `pytest tests/agent tests/events tests/api --cov=agent
--cov=events --cov=api --cov-report=term-missing` passed with 91 tests;
agent coverage 87%. `ruff check agent events api tests/agent tests/events
tests/api` passed. `pyright agent events api tests/agent tests/events
tests/api` reported 0 errors.
