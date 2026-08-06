---
description: "Use when creating or modifying Python backend code in backend/. Prioritize architecture boundaries, strict typing, and pytest coverage."
name: "Backend Architecture And Quality"
applyTo: "backend/**/*.py"
---

# Backend Architecture And Quality

> See `docs/architecture.md` §5 for the full module tree, responsibility matrix, and dependency rules.

## Language And Typing

- Target Python 3.12. Prefer standard library features such as `typing.override`, `pathlib`, `dataclasses`, `enum.StrEnum`, and structural pattern matching when they fit existing style. Add new runtime dependencies only when the standard library or existing project dependencies cannot meet the requirement. In such cases, document the need in the relevant README or design note.
- Write backend code so it is compatible with `pyright --strict`. Fully annotate public APIs and non-trivial internal functions, avoid untyped `Any`, prefer explicit domain types, and structure code so strict checking can pass. The active Pyright scope is currently defined in `backend/pyproject.toml`.

## Module Structure

- The backend is organized into focused modules:

| Concern | Modules |
| --- | --- |
| API and orchestration | `api/`, `agent/`, `events/` |
| Knowledge pipeline | `ingestion/` (documents), `records/` (structured/tabular), `graph/`, `vectorstore/`, `embeddings/`, `rag/`, `llm/`, `knowledgebases/` |
| Analytics and monitoring | `analytics/timeseries/`, `analytics/gnn/`, `analytics/risk/`, `analytics/explainability/`, `analytics/metrics/`, `analytics/peerstats/`, `analytics/features/`, `analytics/identity_resolution/`, `analytics/score_runs/`, `monitoring/`, `scorecards/` |
| Analyst workflows | `cases/`, `conversations/`, `policy/`, `playbooks/` |
| Governance and provenance | `auditlog/` (append-only material-action ledger), `governance/` (release readiness, eval runs, baseline approval) |
| Agentic workflow platform | `workflow_definitions/` (user-authored definitions), `capabilities/` (typed capability/tool registry) |
| Data sources and readiness | `connectors/` (pull connectors), `readiness/` (KB/domain readiness aggregation) |
| Shared platform services | `shared/`, `config/`, `storage/`, `database/` |

> This table is the "where does new code go" map and is auto-applied to every
> `backend/**/*.py`. It omitted ten real packages for the whole SAFE-CMS surge —
> the seven new top-level modules plus the three new `analytics/` submodules —
> so it pointed at a module layout that no longer existed. There are **28**
> backend packages; `ls backend/` is the check.

- Keep modules loosely coupled and narrowly scoped. Each module owns its internal implementation and exposes a narrow public contract.
- The `api/` module is a FastAPI gateway — thin routing, request validation, and dependency injection. **No business logic in routers.**
- The `shared/` module provides stable domain types (`Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`), config-definition types, protocol definitions, and small utilities. It must stay dependency-light and must never contain business logic.

## Cross-Module Interaction

- Do not let backend feature modules reach into each other through ad hoc imports, hidden shared state, or direct implementation coupling.
- Cross-module interaction must happen only through one of these paths:
  - **Path A**: Orchestration through the FastAPI gateway when a frontend-initiated API boundary is appropriate.
  - **Path B**: Orchestration through the agent/workflow coordinator (`agent/coordinator.py`) when the interaction is process-driven, using events via Redis Streams.
  - **Path C**: A lightweight shared library (`shared/`) for stable contracts, shared types, or small reusable utilities.
- If a cross-module interaction does not fit these paths, escalate it for architecture review before implementing it.
- Shared libraries must stay small and dependency-light. Do not turn a shared package into a dumping ground for business logic or a back door for tight coupling.

## Interface And Adapter Pattern

- Prefer interface-first design. Depend on protocols, abstract base classes, or narrow contracts instead of concrete vendor or storage implementations.
- Avoid vendor lock-in in storage, graph, vector store, LLM, embedding, and object storage integrations. Put external-system specifics behind adapters in the relevant module's `adapters/` sub-package.
- Service-level protocols live in the parent module's `protocols.py`; adapter-level ports live in the relevant `adapters/protocols.py`.

## Event-Driven Pipeline

- Pipeline orchestration uses Redis Streams. The `events/` module provides an abstract `EventBus` protocol with a Redis Streams adapter.
- Pipeline stages communicate through typed events (`documents.uploaded`, `entities.extracted`, `graph.updated`, `timeseries.analyzed`, `gnn.analyzed`, `risk.scored`, `explainability.generated`, `alerts.created`, etc.).
- Workers consume events via Redis consumer groups, enabling horizontal scaling.

## Testing

- Add or update pytest coverage for backend changes. Backend test suites should pass and maintain at least 85% coverage for the affected backend package or the backend test target being introduced.
- Treat missing tests as incomplete work for backend features, orchestration paths, adapters, and shared contracts.
- Keep tests isolated and deterministic. Mock or fake external systems at the adapter boundary rather than leaking network, database, or model dependencies into unit tests.
- CI enforces both gates: bare `pyright` (strict scope from `tool.pyright.include` in `backend/pyproject.toml`) and `pytest --cov --cov-fail-under=85` (aggregate; ≥ 85% per touched package is the review standard).
