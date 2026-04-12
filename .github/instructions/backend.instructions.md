---
description: "Use when creating or modifying Python backend modules, services, tests, or architecture in backend/. Enforces Python 3.12, strict type checking, loose coupling, modular boundaries, restricted cross-module interaction, and pytest coverage requirements."
name: "Backend Architecture And Quality"
applyTo: "backend/**/*.py"
---

# Backend Architecture And Quality

> See `docs/architecture.md` §5 for the full module tree, responsibility matrix, and dependency rules.

## Language And Typing

- Target Python 3.12. Use Python 3.12 syntax and standard library features when they improve clarity, but do not introduce dependencies that weaken portability without a concrete need.
- Write backend code so it is compatible with `pyright --strict`. Fully annotate public APIs and non-trivial internal functions, avoid untyped `Any`, prefer explicit domain types, and structure code so strict checking can pass once configured.

## Module Structure

- The backend is organized into 16 modules: `api/`, `ingestion/`, `graph/`, `vectorstore/`, `embeddings/`, `rag/`, `llm/`, `analytics/` (with sub-modules `timeseries/`, `gnn/`, `risk/`, `explainability/`), `agent/`, `monitoring/`, `shared/`, `config/`, `events/`, `storage/`.
- Keep modules loosely coupled and narrowly scoped. Each module owns its internal implementation and exposes a narrow public contract.
- The `api/` module is a FastAPI gateway — thin routing, request validation, and dependency injection. **No business logic in routers.**
- The `shared/` module provides stable domain types (`Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`), config-definition types, protocol definitions, and small utilities. It must stay dependency-light and must never contain business logic.

## Cross-Module Interaction

- Do not let backend feature modules reach into each other through ad hoc imports, hidden shared state, or direct implementation coupling.
- Cross-module interaction must happen only through one of these paths:
  - **Path A**: Orchestration through the FastAPI gateway when a frontend-initiated API boundary is appropriate.
  - **Path B**: Orchestration through the agent/workflow coordinator (`agent/coordinator.py`) when the interaction is process-driven, using events via Redis Streams.
  - **Path C**: A lightweight shared library (`shared/`) for stable contracts, shared types, or small reusable utilities.
- Shared libraries must stay small and dependency-light. Do not turn a shared package into a dumping ground for business logic or a back door for tight coupling.

## Interface And Adapter Pattern

- Prefer interface-first design. Depend on protocols, abstract base classes, or narrow contracts instead of concrete vendor or storage implementations.
- Avoid vendor lock-in in storage, graph, vector store, LLM, embedding, and object storage integrations. Put external-system specifics behind adapters in the relevant module's `adapters/` sub-package.
- Every adapter implements the abstract protocol defined in the parent module's `protocols.py`.

## Event-Driven Pipeline

- Pipeline orchestration uses Redis Streams. The `events/` module provides an abstract `EventBus` protocol with a Redis Streams adapter.
- Pipeline stages communicate through typed events (`documents.uploaded`, `entities.extracted`, `graph.updated`, `analysis.complete`, `alerts.created`, etc.).
- Workers consume events via Redis consumer groups, enabling horizontal scaling.

## Testing

- Add or update pytest coverage for backend changes. Backend test suites should pass and maintain at least 85% coverage for the affected backend package or the backend test target being introduced.
- Treat missing tests as incomplete work for backend features, orchestration paths, adapters, and shared contracts.
- Keep tests isolated and deterministic. Mock or fake external systems at the adapter boundary rather than leaking network, database, or model dependencies into unit tests.
- If repository tooling is not yet in place for strict type checking or coverage enforcement, still write code and tests to satisfy these requirements and add the minimal supporting configuration only when the task calls for it.
