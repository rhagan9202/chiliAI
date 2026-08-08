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
- External systems must sit behind protocols/ABCs with concrete adapters: graph DB, vector store, LLM, object storage, embedding model, event bus, and relational DB (Postgres/TimescaleDB via the `database/` module's `ConnectionProvider` protocol).
- Domain configuration is a single YAML/JSON surface. The frontend reads it at startup via API to render dynamic labels and feature gates. Do not hardcode domain entities in code.
- Frontend HTTP DTOs are generated from backend OpenAPI. Use `chili_app/src/api/contracts.ts` aliases for API shapes; do not hand-write `*Request` or `*Response` wire types in frontend code. Domain configuration remains runtime data: do not hardcode domain entity names, relationship names, record fields, or capability values.
- FastAPI and Redis Streams are mandatory architectural components; do not replace them without an explicit architecture update.
- For new backend modules, follow the package tree and responsibility matrix in `docs/architecture.md` §5.

## Current Implementation Map

- `backend/` is a Python 3.12 FastAPI/API + worker prototype with service/protocol modules, routers, adapters, and tests. See `backend/README.md` for current status and `docs/backlog/README.md` (with per-module files under `docs/backlog/`) for production-readiness gaps and dependency-ordered work items.
- Backend has **28 packages** (`ls backend/` is ground truth): `api/`, `ingestion/`, `graph/`, `vectorstore/`, `embeddings/`, `rag/`, `llm/`, `analytics/` (timeseries, gnn, risk, explainability, metrics, peerstats, features, identity_resolution, score_runs), `agent/`, `monitoring/`, `shared/`, `config/`, `events/`, `storage/`, `database/` (Postgres + TimescaleDB connection provider, Alembic migrations), `records/` (structured/tabular ingestion: CSV/JSONL/api-push, raw_records landing — parallel to `ingestion/` for documents), `scorecards/` (config-driven deterministic scorecard evaluation with persisted runs), `knowledgebases/`, `cases/`, `conversations/`, `policy/`, plus the SAFE-CMS surge modules: `auditlog/` (append-only material-action ledger), `playbooks/` (versioned fraud playbooks), `workflow_definitions/` (user-authored workflows), `capabilities/` (typed capability/tool registry), `connectors/` (pull connectors), `readiness/` (KB/domain readiness), and `governance/` (release readiness + eval runs).
- `chili_app/` is a routed analyst workbench, not a Vite placeholder. Implemented routes include Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, and Configuration, plus capability-gated domain pages (Case Management, Policy Intelligence, Housing Executive, Scorecard Run viewer).
- Known frontend prototype gaps include the sectioned configuration wizard (post-v1; the validated raw-YAML editor + pack switcher shipped) and production UX/performance hardening. See `chili_app/README.md` for route status.
- Runtime topology is three app containers: **chili-app** (React SPA/nginx), **chili-api** (FastAPI gateway), and **chili-worker** (pipeline runner), plus Redis 7+, graph DB, vector store, and object store dependencies. See `docs/architecture.md` §4.

## Tooling And Commands

- Package managers: uv for Python environment management (`uv venv`, `uv pip install …`; no bare `pip`, pipenv, or poetry), npm for node/TypeScript (no pnpm or yarn). Day-to-day backend tools run from the project venv (`backend/.venv/bin/…` or an activated venv). Current frontend commands are defined in `chili_app/package.json` and use npm scripts:
  - `npm run dev` — Vite dev server
  - `npm run build` — TypeScript compile + Vite production build
  - `npm run lint` — ESLint
- Backend uses Python 3.12 as declared in `backend/.python-version` and `backend/pyproject.toml`:
  - API server: `uvicorn api.app:create_app --factory --reload --port 8000`
  - Worker: `python -m agent.coordinator`
  - Tests: `pytest --cov` — DB-touching tests default to the `chili_test` scratch DB (conftest; created on fresh dev volumes by `infra/postgres/init-test-db.sql`, and self-provisioned to `alembic upgrade head` by a session-scoped conftest fixture when the schema is missing). ⚠️ Never export the dev `chili` DSN as `DATABASE_URL` for a test run: the migration tests downgrade/upgrade against it and empty every app table (see `backend/README.md`).
  - Type check/lint: `pyright`, `ruff check .`
- CI runs backend lint/typecheck/tests and frontend lint/typecheck/tests/build. Keep touched areas green.
- Tooling gotchas (mirrored from `CLAUDE.md` — keep in sync):
  - `ruff`'s cache dir may not be writable in sandboxed agent runs — use `ruff check --no-cache .`.
  - Bare `pyright` (no args) is the real gate — `tool.pyright.include` covers many `tests/**`, so test code must be strict-clean too; per-file `pyright <file>` can miss include-scoped test errors.
  - The repo-root `tools/` package is typechecked by its own `tools/pyrightconfig.json` (a separate CI step, "Type-check tools/"), not folded into `backend/pyproject.toml`'s `[tool.pyright]`, whose `include` is scoped to `backend/`. The split originated with a since-deleted `backend/tools/` that shared the bare name (removed 2026-07-24); it is kept for isolation, not for a live collision.
  - Playwright `page.route` patterns must be `/api/`-anchored — unanchored patterns also intercept SPA page navigations and render JSON as the page body.
  - Regenerate frontend contracts after ANY frontend-consumed Pydantic change: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` (repo root), then `cd chili_app && npm run codegen:api`. CI fails on drift.

## Quality Gates

- Backend functional code must be fully typed, compatible with `pyright --strict`, and avoid untyped `Any`. The active Pyright scope is in `backend/pyproject.toml`.
- Backend changes require pytest coverage ≥ 85% for affected packages and full green tests before acceptance (per-package is the project standard; the CI gate enforces the aggregate `--cov-fail-under=85`).
- Frontend TypeScript is strict (`noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`) and must remain ESLint clean.
- Follow existing frontend patterns: functional React components, hooks, Vite/ESLint setup, TanStack Query for server state, Zustand for client state, and React Router v8 for routing.
- Use e2e/Playwright verification for workflows, UI behavior, and integration points. E2E tests MUST run against the full running stack (real API + worker + services, e.g. `make dev`); `page.route`/mock fixtures must never stand in for the component, endpoint, or integration under test — a test whose subject is mocked is not an e2e test.
- Never silence errors, suppress warnings, bypass type checks, or leave known errors as TODOs. Fix relevant errors when found; import-order-only issues are the exception.
- DO NOT LEAVE PRE-EXISTING ERRORS, including failures you surface by running a suite/build (a red test, type error, or lint failure in code you did not write): root-cause and fix them — do not flag them as "pre-existing" or "unrelated." Do not end a turn with any known error, warning, or failing test outstanding.
- Repo-level gates run via `make check`: `scripts/backlog_consistency.py --check` and `scripts/security_review_check.py`. Both also run in CI.
- Dependency audits gate on HIGH/CRITICAL (`pip-audit`, `npm audit --audit-level=high`, plus a nightly sweep). To suppress an advisory, add it to `.github/security_accepted.yaml` with a rationale, an owner and a `review_by` date — never an inline `--ignore-vuln` flag. `scripts/security_review_check.py` fails CI once a `review_by` passes, and once the quarterly security review is more than 30 days overdue (`.github/workflows/security_review_reminder.yml` opens the tracking issue).

## Agent Workflow Rules

- When planning, read the nearest `README.md` files and applicable instruction files (`CLAUDE.md`, this file, `.github/instructions/*.md`), and document assumptions/open questions instead of fabricating details.
- When implementing, update adjacent docs for new commands, dependencies, APIs, or architectural decisions. Update `docs/architecture.md` and the root `README.md` for design or cross-cutting changes.
- When changing frontend behavior, run and visually/interaction-test the app when practical; do not rely only on code review.
- When changing backend behavior, run relevant tests and, when practical, verify API/worker behavior, logs, and persisted state.
- Before committing broad or cross-cutting work, check `CLAUDE.md`, `.github/` instructions, module READMEs, and non-archived docs for contradictions or outdated guidance.
