# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Rules
- Use uv for python environment management (`uv venv`, `uv pip install …`), npm for node and typescript. Day-to-day tool invocation goes through the project venv (`backend/.venv/bin/pytest`, activated-venv `pytest`, etc.). Do not use bare `pip`, pipenv, poetry, pnpm, or yarn.
- Use Python 3.12 and React 19 with Vite 8.
- All functional code must be fully typed with no `Any` types. Use `pyright --strict` to check.
- All functional backend code must have pytest coverage >= 85% coverage, full green before acceptance.
- All frontend code must have TypeScript strict mode enabled and be ESLint clean.
- Use e2e tests and Playwright to verify workflows, UI elements, and integration points. E2E tests MUST run against the full running stack (real API + worker + services, e.g. `make dev`); never let `page.route`/mock fixtures stand in for the component, endpoint, or integration under test — if the subject of the test is mocked, it is not an e2e test and does not count as verification.
- When changing frontend behavior, run the app and verify proper rendering and interactions; do not rely solely on code review.
- When changing backend behavior, run the API and worker locally, and verify expected logs, database state, and API responses; do not rely solely on code review.
- Never silence errors, suppress warnings, or bypass type checks to get acceptance. Address the underlying issue instead.
- Correct all errors, warnings and type errors as soon as they are found. Do NOT leave them for later, ignore as pre-existing, mark with TODO, or skip as out of scope or not my code. If you see it, fix it before proceeding. The only exception is ignore import order. This is non-negotiable.
- DO NOT LEAVE PRE-EXISTING ERRORS. This includes failures you surface by running a suite/build (a red test, a type error, a lint failure in code you did not write): diagnose the root cause and fix it — do not merely flag it as "pre-existing" or "unrelated." You may NOT end your turn with any known error, warning, or failing test outstanding.
- When finishing a turn, read and update the relevant module README.md files and any applicable instruction files under `.github/` (for example `.github/copilot-instructions.md` and `.github/instructions/*.md`).
- When finishing a turn update the architecture.md file and the root README.md if the change affects design or cross-cutting concerns.
- Before committing, read CLAUDE.md, all instruction files in `.github/`, all README.md files in the repo, and all non-archived files in docs/ and update any contradictions or outdated information.
- When planning a change, search up the directory for the nearest README.md files and applicable instruction files (CLAUDE.md, `.github/copilot-instructions.md`, `.github/instructions/*.md`) to understand the current state and relevant constraints.

### Tooling gotchas (cost real time; will recur)
- **Host `pytest --cov` WIPES the dev-stack Postgres data**: `DATABASE_URL` defaults to the dev stack's `…:5432/chili`, and `tests/database/test_migrations.py` runs `alembic downgrade base` → `upgrade head` against it, emptying every app table while KB shells survive in the object store. When the stack holds seeded/demo state, run `DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test pytest --cov` (details: `backend/README.md` § Development Commands).
- `ruff`'s cache dir is not writable in the sandbox — run `backend/.venv/bin/ruff check --no-cache .`.
- Bare `pyright` (no args) is the real gate — its `tool.pyright.include` covers many `tests/**`, so test code must be strict-clean too. Never import private `_helpers` into an included test dir (triggers `reportPrivateUsage`); test through the public surface (promote a helper to public if needed). Per-file `pyright <file>` can miss include-scoped test errors.
- Playwright `page.route` patterns must be `/api/`-anchored — an unanchored `/cases`-style pattern also intercepts the SPA page navigation `localhost:5173/cases` and renders JSON as the page body.
- Regenerate frontend contracts after ANY frontend-consumed Pydantic change: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` (from repo root), then `cd chili_app && npm run codegen:api`. CI fails on drift.

## Authoritative References

- `docs/architecture.md` — design source of truth (full module decomposition, container topology, domain-config model). Read it before any non-trivial change.
- `.github/copilot-instructions.md` — condensed operating rules for agents (kept consistent with this file).
- `backend/README.md`, `chili_app/README.md` — module/page-level setup details.
- `docs/testing/DATA.md` — **single source of truth for all test/sample data**: the two-tier model (tracked tiny fixtures vs gitignored bulk `sample_data/`), the fixture index (every data location → its consumer), and how to stage the CMS/NPPES bulk data (`make data-setup`). Read before adding any fixture or wiring data into a test/demo.

## What This Repo Is

chiliAI is a **domain-reconfigurable Graph RAG analytics platform**. A single YAML/JSON configuration retargets the same code to different domains (Medicare fraud, food supply chain, etc.). The starting exemplar is Medicare fraud detection.

Monorepo layout: `backend/` (Python 3.12 / FastAPI), `chili_app/` (React 19 + TS + Vite 8), `docs/`, `infra/`. The repo is an active local-development prototype: backend modules, worker orchestration, frontend workbench routes, CI, and baseline deployment manifests exist, while production hardening remains in progress.

## Common Commands

### Full stack (Docker)
```bash
make dev          # docker compose -f docker-compose.dev.yaml up --build (hot reload)
make dev-domain DOMAIN=<pack>  # dev stack under a named domain pack (backend/config/defaults/<pack>.yaml)
make down         # stop dev stack
make clean        # stop + remove volumes
make api-shell    # shell into the API container
make migrate      # alembic upgrade head inside the API container
make test         # run backend pytest --cov inside the API container
make test-e2e     # Playwright e2e against a fresh full dev stack
make seed-housing # seed the Air Force housing demo KB via the running API (housing pack required)
make prod         # production stack (built images, nginx, no hot reload)
```
Service URLs: frontend `:5173`, API `:8000`, Neo4j `:7474`, Qdrant `:6333`, MinIO console `:9001`. `.env` is loaded from `.env.example` (gitignored).

### Backend (`cd backend`)
```bash
uv venv && uv pip install -e ".[dev]"                    # env + base dev tools (uv manages the venv)
uv pip install -e ".[dev,neo4j,qdrant,openai,anthropic,s3,sentence-transformers]"  # with optional adapters
uvicorn api.app:create_app --factory --reload --port 8000  # API (note --factory: create_app is a factory)
python -m agent.coordinator                               # pipeline worker
pytest --cov                                              # all tests; standard is ≥ 85% per package (CI enforces aggregate --cov-fail-under=85)
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
npm run test           # Vitest unit tests (watch mode)
npm run test:run       # Vitest unit tests (single run)
npm run test:e2e       # Playwright e2e tests (starts Vite automatically)
npm run test:e2e:ui    # Playwright UI mode for interactive debugging
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
Every external system is accessed via an abstract `Protocol` in `<module>/protocols.py` with concrete implementations in `<module>/adapters/`. Implemented selectable backends are: graph DB (in-memory, Neo4j), vector store (in-memory, Qdrant), LLM (local, OpenAI, Anthropic, Ollama), embeddings (local, OpenAI, sentence-transformers), object storage (local FS, S3, MinIO), event bus (in-memory, Redis Streams). Roadmap adapters such as Memgraph, Neptune, pgvector, Weaviate, GCS, or vLLM must not be added to `DomainConfig` literals until their adapter and factory wiring exist.

Modules typically expose: `protocols.py` (abstract contract), `models.py` (internal domain models), `service_models.py` (external/API-facing models), `service.py` (orchestration), `adapters/` (concrete impls), `exceptions.py`. New external integrations follow this layout.

### 3. No hardcoded domain types
`shared/types.py` contains only generic platform types (`Entity`, `Relationship`, `Alert`, `EvidencePack`, `KnowledgeBase`). Domain entities are `Entity(type=..., properties=...)` validated against the loaded `DomainConfig`. Never add a `Provider`, `Claim`, or `Beneficiary` class — those are configured, not coded.

### 4. Domain configuration drives everything
`config/schema.py` defines `DomainConfig` (Pydantic). `config/loader.py` loads YAML/JSON. Defaults live in `config/defaults/*.yaml`. Path comes from `CHILI_CONFIG_PATH`. The frontend fetches `GET /config/domain` at startup and renders entity labels, icons, and feature gates dynamically — adding a domain should not require frontend code changes.

### 5. Frontend API contracts are generated from backend OpenAPI
Backend FastAPI OpenAPI is the source of truth for HTTP request/response shapes. Frontend code must import API DTOs from `chili_app/src/api/contracts.ts`, which aliases generated types from `chili_app/src/lib/api/schema.ts`. Do not hand-write frontend wire DTOs, do not edit generated schema files, and do not patch type failures with `as any`. When a frontend-consumed backend route changes, update the Pydantic request/response model, export OpenAPI, run `npm run codegen:api`, then update UI adapters.

### 6. Quality gates
- Backend: `pyright --strict` clean (strictness is scoped by `tool.pyright.include` in `backend/pyproject.toml`; hardened modules are added to `include`), full annotations, no untyped `Any`. pytest coverage ≥ 85% per package is the project standard (CI's enforced gate is the aggregate `--cov-fail-under=85`) — missing tests = incomplete work.
- Frontend: TypeScript strict (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`). ESLint clean.

## Backend Module Map (Target)

`api/` (FastAPI gateway, no business logic) · `ingestion/` (PDF/DOCX/HTML/JSON/TXT parsing, chunking, entity extraction) · `graph/` (graph DB protocol + adapters) · `vectorstore/` (vector store protocol + adapters) · `embeddings/` (embedder protocol + adapters) · `rag/` (query → embed → search → graph expand → LLM) · `llm/` (LLM client protocol + adapters) · `analytics/{timeseries,gnn,risk,explainability,metrics}/` · `agent/` (workflow coordinator) · `monitoring/` (claim stream consumer, alert generation) · `shared/` · `config/` · `events/` (Redis Streams) · `storage/` (object storage adapters) · `database/` (Postgres + TimescaleDB connection provider, Alembic migrations) · `records/` (structured/tabular ingestion: CSV/JSONL/api-push, raw_records landing — parallel to `ingestion/` for documents).

Implementation status varies by module. Verify behavior by reading the code and tests, and use `backend/README.md` § Current State plus `docs/backlog/README.md` (and the per-module files it links) for production-readiness gaps and dependency-ordered work items.

## Container Topology

Three app containers + pluggable infrastructure:
- **chili-app** — React SPA served by nginx in prod
- **chili-api** — FastAPI gateway
- **chili-worker** — pipeline runner consuming Redis Streams

Infra services in dev compose: Redis 7, Neo4j 5, Qdrant, MinIO, Postgres (TimescaleDB). Redis Streams is the event transport (architectural decision, not a placeholder).

## When Planning vs. Implementing

- **Planning tasks** — document assumptions and open questions; do not fabricate implementation details to fill gaps.
- **Implementation tasks** — when introducing a new command, dependency, or architectural decision, update the relevant README (`backend/README.md`, `chili_app/README.md`) and, if it affects design, `docs/architecture.md`.
- Historical story prompts and backlog files are archived under `docs/archive/planning/`; do not treat them as live implementation status.
- Frontend UI/UX reference mockups are in ui_reference_code/ in the root; these are reference only and may not reflect the current codebase state. Always verify against the actual code and tests.
