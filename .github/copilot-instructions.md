# Project Guidelines

> The authoritative architecture reference is `docs/architecture.md`. These guidelines are the condensed operating rules for agents working in this repo.

## Project Scope
- This repository is a monorepo with a Python 3.12 backend in `backend/` and a React 19 + TypeScript frontend in `chili_app/`.
- chiliAI is a domain-reconfigurable Graph RAG analytics platform. The starting exemplar is Medicare fraud detection.
- Treat the top-level `README.md` as product vision and quick-start context. Treat `docs/architecture.md` as the design source of truth.
- Prefer changes that clarify architecture and preserve future modularity over quick, tightly coupled implementations.

## Current Architecture
- `backend/` is a Python 3.12 FastAPI and worker prototype with service/protocol modules, routers, adapters, and tests. See `backend/README.md` for the live implementation surface and `docs/todos_and_stubs_audit_2026-05-05.md` for the current TODO/stub inventory.
- The backend structure is 16 modules: `api/`, `ingestion/`, `graph/`, `vectorstore/`, `embeddings/`, `rag/`, `llm/`, `analytics/` (timeseries, gnn, risk, explainability), `agent/`, `monitoring/`, `shared/`, `config/`, `events/`, `storage/`. See `docs/architecture.md` §5 for the full package tree and responsibility matrix.
- `chili_app/` is a routed React 19 + TypeScript analyst workbench, not the Vite placeholder. Implemented routes include Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, and Configuration.
- The frontend still has prototype gaps around persisted evidence packs, config save, and production UX/performance hardening. See `chili_app/README.md` for current route status.
- Keep frontend and backend concerns separate. Do not invent cross-layer contracts implicitly inside UI code.

## Container Architecture
- The platform deploys as three containers: **chili-app** (React SPA / nginx), **chili-api** (FastAPI gateway), and **chili-worker** (pipeline runner consuming Redis Streams).
- External dependencies: Redis 7+ (event streaming), a pluggable graph database, a pluggable vector store, and a pluggable object store.
- See `docs/architecture.md` §4 for full container diagram and communication patterns.

## Build And Test
- Frontend commands live in `chili_app/package.json`:
  - `npm run dev` — Vite dev server
  - `npm run build` — TypeScript compile + Vite production build
  - `npm run lint` — ESLint
- Backend uses Python 3.12 as declared in `backend/.python-version` and `backend/pyproject.toml`.
  - Target API server: `uvicorn api.app:create_app --reload --port 8000`
  - Target worker: `python -m agent.coordinator`
  - Tests: `pytest --cov` (≥ 85% coverage required per backend package)
- CI runs backend lint/typecheck/tests and frontend lint/typecheck/tests/build. Keep touched areas green and document new commands in the relevant README.

## Conventions
- Preserve the monorepo split: frontend work in `chili_app/`, backend work in `backend/`, design docs in `docs/`, deployment config in `infra/`.
- Frontend TypeScript is strict: `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`. Keep builds and lint clean.
- Follow existing frontend patterns: functional React components, hooks, and the current Vite/ESLint setup. Target libraries: TanStack Query for server state, Zustand for client state, React Router v7 for routing.
- Backend code must be compatible with `pyright --strict` — full annotations, no untyped `Any`, explicit domain types.
- Design around abstract interfaces (protocols, ABCs) and interchangeable adapters for all external systems: graph DB, vector store, LLM, object storage.
- Domain configuration is a single YAML/JSON surface. The frontend reads it at startup via API to render dynamic labels and feature gates. See `docs/architecture.md` §9.

## Cross-Module Interaction Rules
Backend modules may only interact through these three paths:
1. **FastAPI gateway orchestration** — for frontend-initiated actions (API router → service modules).
2. **Agent / workflow coordinator** — for process-driven multi-step pipelines (events via Redis Streams).
3. **Lightweight shared library** (`shared/`) — for stable contracts, domain types, and small utilities.

**Forbidden**: ad hoc cross-module imports, hidden shared state, direct implementation coupling.

## Working Rules For Agents
- FastAPI is the chosen API framework. Redis Streams is the event transport. These are architectural decisions, not assumptions.
- For new backend modules, follow the package tree in `docs/architecture.md` §5. Establish module boundaries first and avoid coupling concerns.
- Every external system (graph DB, vector store, LLM, object store, embedding model) must be behind an abstract protocol with concrete adapters.
- Backend changes must include pytest tests maintaining ≥ 85% coverage for the affected package.
- For planning tasks, prefer documenting assumptions and open questions instead of fabricating missing implementation details.
- For implementation tasks, update adjacent docs when you introduce a new command, dependency, or architectural decision.
