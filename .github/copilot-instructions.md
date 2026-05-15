# Project Guidelines

> `docs/architecture.md` is the design source of truth. This file is the condensed operating guide for agents working in this repo; keep it aligned with `CLAUDE.md`, the root `README.md`, and module READMEs.

## Project Scope

- chiliAI is a domain-reconfigurable Graph RAG analytics platform. The starting exemplar is Medicare fraud detection.
- Prefer changes that clarify architecture, preserve modularity, and avoid tight coupling.
- Keep frontend and backend concerns separate. Do not invent cross-layer contracts implicitly inside UI code.

| Area | Location | Stack / purpose |
| --- | --- | --- |
| Backend | `backend/` | Python 3.12 FastAPI API and worker |
| Frontend | `chili_app/` | React 19 + TypeScript/Vite 8 workbench |
| Design docs | `docs/` | Architecture and planning source material |
| Deployment | `infra/` | Infrastructure and runtime assets |

## Architecture Guardrails

- Backend modules may communicate only through:
  1. **FastAPI gateway orchestration** — frontend-initiated actions via API routers and service modules.
  2. **Agent / workflow coordinator** — process-driven pipelines over Redis Streams.
  3. **Lightweight shared library** (`shared/`) — stable contracts, domain types, and small utilities.
- **Forbidden**: ad hoc cross-module imports, hidden shared state, and direct implementation coupling.
- External systems must sit behind protocols/ABCs with concrete adapters: graph DB, vector store, LLM, object storage, embedding model, and event bus.
- Domain configuration is a single YAML/JSON surface. The frontend reads it at startup via API to render dynamic labels and feature gates. Do not hardcode domain entities in code.
- FastAPI and Redis Streams are mandatory architectural components; do not replace them without an explicit architecture update.
- For new backend modules, follow the package tree and responsibility matrix in `docs/architecture.md` §5.

## Current Implementation Map

- `backend/` is a Python 3.12 FastAPI/API + worker prototype with service/protocol modules, routers, adapters, and tests. See `backend/README.md` and `docs/todos_and_stubs_audit_2026-05-05.md` for current status.
- Backend modules include `api/`, `ingestion/`, `graph/`, `vectorstore/`, `embeddings/`, `rag/`, `llm/`, `analytics/` (timeseries, gnn, risk, explainability), `agent/`, `monitoring/`, `shared/`, `config/`, `events/`, and `storage/`.
- `chili_app/` is a routed analyst workbench, not a Vite placeholder. Implemented routes include Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, and Configuration.
- Known frontend prototype gaps include persisted evidence packs, config save, and production UX/performance hardening. See `chili_app/README.md` for route status.
- Runtime topology is three app containers: **chili-app** (React SPA/nginx), **chili-api** (FastAPI gateway), and **chili-worker** (pipeline runner), plus Redis 7+, graph DB, vector store, and object store dependencies. See `docs/architecture.md` §4.

## Tooling And Commands

- Follow existing lockfiles and module READMEs for package managers. Current frontend commands are defined in `chili_app/package.json` and use npm scripts:
  - `npm run dev` — Vite dev server
  - `npm run build` — TypeScript compile + Vite production build
  - `npm run lint` — ESLint
- Backend uses Python 3.12 as declared in `backend/.python-version` and `backend/pyproject.toml`:
  - API server: `uvicorn api.app:create_app --factory --reload --port 8000`
  - Worker: `python -m agent.coordinator`
  - Tests: `pytest --cov`
  - Type check/lint: `pyright`, `ruff check .`
- CI runs backend lint/typecheck/tests and frontend lint/typecheck/tests/build. Keep touched areas green.

## Quality Gates

- Backend functional code must be fully typed, compatible with `pyright --strict`, and avoid untyped `Any`. The active Pyright scope is in `backend/pyproject.toml`.
- Backend changes require pytest coverage ≥ 85% for affected packages and full green tests before acceptance.
- Frontend TypeScript is strict (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`) and must remain ESLint clean.
- Follow existing frontend patterns: functional React components, hooks, Vite/ESLint setup, TanStack Query for server state, Zustand for client state, and React Router v7 for routing.
- Use e2e/Playwright verification for workflows, UI behavior, and integration points when practical.
- Never silence errors, suppress warnings, bypass type checks, or leave known errors as TODOs. Fix relevant errors when found; import-order-only issues are the exception.

## Agent Workflow Rules

- When planning, read nearby `README.md`, `AGENT_Instructions.md`, or `AGENT.md` files if present, and document assumptions/open questions instead of fabricating details.
- When implementing, update adjacent docs for new commands, dependencies, APIs, or architectural decisions. Update `docs/architecture.md` and the root `README.md` for design or cross-cutting changes.
- When changing frontend behavior, run and visually/interaction-test the app when practical; do not rely only on code review.
- When changing backend behavior, run relevant tests and, when practical, verify API/worker behavior, logs, and persisted state.
- Before committing broad or cross-cutting work, check `CLAUDE.md`, `.github/` instructions, module READMEs, and non-archived docs for contradictions or outdated guidance.