# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Authoritative References

- `docs/architecture.md` — design source of truth (full module decomposition, container topology, domain-config model). Read it before any non-trivial change.
- `.github/copilot-instructions.md` — condensed operating rules for agents (kept consistent with this file).
- `backend/README.md`, `chili_app/README.md` — module/page-level setup details.

## What This Repo Is

chiliAI is a **domain-reconfigurable Graph RAG analytics platform**. A single YAML/JSON configuration retargets the same code to different domains (Medicare fraud, food supply chain, etc.). The starting exemplar is Medicare fraud detection.

Monorepo layout: `backend/` (Python 3.12 / FastAPI), `chili_app/` (React 19 + TS + Vite 8), `docs/`, `infra/`. Both halves are scaffolds in early stages — much of the target architecture is not yet implemented.

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
Every external system is accessed via an abstract `Protocol` in `<module>/protocols.py` with concrete implementations in `<module>/adapters/`. This applies to: graph DB (Neo4j/Memgraph/Neptune), vector store (pgvector/Qdrant/Weaviate), LLM (OpenAI/Anthropic/Ollama), embeddings (OpenAI/sentence-transformers), object storage (S3/MinIO/local FS), event bus (Redis Streams).

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

Implementation status varies — assume modules are scaffold-only unless verified by reading the code. The current functional surface is documented in `backend/README.md` § Current State.

## Container Topology

Three app containers + pluggable infrastructure:
- **chili-app** — React SPA served by nginx in prod
- **chili-api** — FastAPI gateway
- **chili-worker** — pipeline runner consuming Redis Streams

Infra services in dev compose: Redis 7, Neo4j 5, Qdrant, MinIO. Redis Streams is the event transport (architectural decision, not a placeholder).

## When Planning vs. Implementing

- **Planning tasks** — document assumptions and open questions; do not fabricate implementation details to fill gaps.
- **Implementation tasks** — when introducing a new command, dependency, or architectural decision, update the relevant README (`backend/README.md`, `chili_app/README.md`) and, if it affects design, `docs/architecture.md`.
- Story prompts and backlog live in `docs/planning/`.
