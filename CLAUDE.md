# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Rules
- Use uv for python environment management, pnpm for node and typescript. Do not use pipenv, poetry, npm, or yarn.
- Use Python 3.12 and React 19 with Vite 8.
- All functional code must be fully typed with no `Any` types. Use `pyright --strict` to check.
- All functional backend code must have pytest coverage >= 85% coverage, full green before acceptance.
- All frontend code must have TypeScript strict mode enabled and be ESLint clean.
- Use e2e tests and playwright to verify workflows, UI elements, and integration points.
- When changing frontend behavior, run the app and verify proper rendering and interactions; do not rely solely on code review.
- When changing backend behavior, run the API and worker locally, and verify expected logs, database state, and API responses; do not rely solely on code review.
- Never silence errors, suppress warnings, or bypass type checks to get acceptance. Address the underlying issue instead.
- Correct all errors, warnings and type errors as soon as they are found. Do NOT leave them for later, ignore as pre-existing, mark with TODO, or skip as out of scope or not my code. If you see it, fix it before proceeding. The only exception is ignore import order. This is non-negotiable.
- When finishing a turn, read and update the README.md, AGENT_Instructions.md, and AGENT.md files in the relevant module(s).
- When finishing a turn update the architecture.md file and the root README.md if the change affects design or cross-cutting concerns.
- Before committing, read CLAUDE.md, all instruction files in github/, all README.md files in the repo, and all non-archived files in docs/ and update any contradictions or outdated information.
- When planning a change, search up the directory for the nearest README.md, AGENT_Instructions.md, and AGENT.md files and read them to understand the current state and any relevant instructions.

## Authoritative References

- `docs/architecture.md` — design source of truth (full module decomposition, container topology, domain-config model). Read it before any non-trivial change.
- `.github/copilot-instructions.md` — condensed operating rules for agents (kept consistent with this file).
- `backend/README.md`, `chili_app/README.md` — module/page-level setup details.

## What This Repo Is

chiliAI is a **domain-reconfigurable Graph RAG analytics platform**. A single YAML/JSON configuration retargets the same code to different domains (Medicare fraud, food supply chain, etc.). The starting exemplar is Medicare fraud detection.

Monorepo layout: `backend/` (Python 3.12 / FastAPI), `chili_app/` (React 19 + TS + Vite 8), `docs/`, `infra/`. The repo is an active local-development prototype: backend modules, worker orchestration, frontend workbench routes, CI, and baseline deployment manifests exist, while production hardening remains in progress.

## Common Commands

### Full stack (Docker)
```bash
make dev          # docker compose -f docker-compose.dev.yaml up --build (hot reload)
make down         # stop dev stack
make clean        # stop + remove volumes
make api-shell    # shell into the API container
make test         # run backend pytest --cov inside the API container
make prod         # production stack (built images, nginx, no hot reload)
```
Service URLs: frontend `:5173`, API `:8000`, Neo4j `:7474`, Qdrant `:6333`, MinIO console `:9001`. `.env` is loaded from `.env.example` (gitignored).

### Backend (`cd backend`)
```bash
pip install -e ".[dev]"                                  # base + dev tools
pip install -e ".[dev,neo4j,qdrant,openai,anthropic,s3,sentence-transformers]"  # with optional adapters
uvicorn api.app:create_app --factory --reload --port 8000  # API (note --factory: create_app is a factory)
python -m agent.coordinator                               # pipeline worker
pytest --cov                                              # all tests, coverage gate ≥ 85% per package
pytest tests/storage/test_in_memory.py::TestClass::test_x # single test
pytest -m integration                                     # tests requiring external services / optional deps
pyright                                                   # strict type check (config in pyproject.toml)
ruff check .                                              # lint
```

Optional dependencies are split per adapter (`[neo4j]`, `[qdrant]`, `[openai]`, `[anthropic]`, `[s3]`, `[sentence-transformers]`). Tests for optional adapters are marked `@pytest.mark.integration` and skipped unless the extra is installed.

`pyright` is currently scoped via `tool.pyright.include` in `pyproject.toml` — when a module is hardened to strict mode, add it to `include`.

### Frontend (`cd chili_app`)
```bash
npm install
npm run dev       # Vite on :5173
npm run build     # tsc -b && vite build
npm run lint      # ESLint
npm run preview
```

## Architecture: Hard Rules (Don't Break These)

These are architectural decisions, not assumptions. Violating them is the most common way changes drift the codebase off its intended shape.

### 1. Cross-module interaction is restricted to three paths
Backend modules may communicate **only** through:
1. **FastAPI gateway** (`api/`) — for frontend-initiated requests; routers depend on services via DI.
2. **Agent / workflow coordinator** (`agent/`) — for multi-step pipelines, communicating via Redis Streams events.
3. **Shared contracts library** (`shared/`) — domain types, protocols, small utilities only. Dependency-light, no business logic.

Forbidden: ad-hoc cross-module imports (e.g. `rag/` importing from `ingestion/` directly), hidden shared state, direct implementation coupling between modules.

### 2. External systems live behind protocols + adapters
Every external system is accessed via an abstract `Protocol` in `<module>/protocols.py` with concrete implementations in `<module>/adapters/`. Implemented selectable backends are: graph DB (in-memory, Neo4j), vector store (in-memory, Qdrant), LLM (local, OpenAI, Anthropic), embeddings (local, OpenAI, sentence-transformers), object storage (local FS, S3, MinIO), event bus (in-memory, Redis Streams). Roadmap adapters such as Memgraph, Neptune, pgvector, Weaviate, GCS, or Ollama/vLLM must not be added to `DomainConfig` literals until their adapter and factory wiring exist.

Modules typically expose: `protocols.py` (abstract contract), `models.py` (internal domain models), `service_models.py` (external/API-facing models), `service.py` (orchestration), `adapters/` (concrete impls), `exceptions.py`. New external integrations follow this layout.

### 3. No hardcoded domain types
`shared/types.py` contains only generic platform types (`Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`). Domain entities are `Entity(type=..., properties=...)` validated against the loaded `DomainConfig`. Never add a `Provider`, `Claim`, or `Beneficiary` class — those are configured, not coded.

### 4. Domain configuration drives everything
`config/schema.py` defines `DomainConfig` (Pydantic). `config/loader.py` loads YAML/JSON. Defaults live in `config/defaults/*.yaml`. Path comes from `CHILI_CONFIG_PATH`. The frontend fetches `GET /config/domain` at startup and renders entity labels, icons, and feature gates dynamically — adding a domain should not require frontend code changes.

### 5. Quality gates
- Backend: `pyright --strict` clean, full annotations, no untyped `Any`. pytest coverage ≥ 85% per package — missing tests = incomplete work.
- Frontend: TypeScript strict (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`). ESLint clean.

## Backend Module Map (Target)

`api/` (FastAPI gateway, no business logic) · `ingestion/` (PDF/DOCX/HTML/JSON/TXT parsing, chunking, entity extraction) · `graph/` (graph DB protocol + adapters) · `vectorstore/` (vector store protocol + adapters) · `embeddings/` (embedder protocol + adapters) · `rag/` (query → embed → search → graph expand → LLM) · `llm/` (LLM client protocol + adapters) · `analytics/{timeseries,gnn,risk,explainability}/` · `agent/` (workflow coordinator) · `monitoring/` (claim stream consumer, alert generation) · `shared/` · `config/` · `events/` (Redis Streams) · `storage/` (object storage adapters).

Implementation status varies by module. Verify behavior by reading the code and tests, and use `backend/README.md` § Current State plus `docs/todos_and_stubs_audit_2026-05-05.md` for the current TODO/stub inventory.

## Container Topology

Three app containers + pluggable infrastructure:
- **chili-app** — React SPA served by nginx in prod
- **chili-api** — FastAPI gateway
- **chili-worker** — pipeline runner consuming Redis Streams

Infra services in dev compose: Redis 7, Neo4j 5, Qdrant, MinIO. Redis Streams is the event transport (architectural decision, not a placeholder).

## When Planning vs. Implementing

- **Planning tasks** — document assumptions and open questions; do not fabricate implementation details to fill gaps.
- **Implementation tasks** — when introducing a new command, dependency, or architectural decision, update the relevant README (`backend/README.md`, `chili_app/README.md`) and, if it affects design, `docs/architecture.md`.
- Historical story prompts and backlog files are archived under `docs/archive/planning/`; do not treat them as live implementation status.
- Frontend UI/UX reference mockups are in ui_reference_code/ in the root; these are reference only and may not reflect the current codebase state. Always verify against the actual code and tests.
