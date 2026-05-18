# chiliAI — Developer Onboarding Guide

> **Read this first.** It is the single document a new contributor needs to go from zero to productive.
> Authoritative design details live in [`docs/architecture.md`](architecture.md). This guide does not repeat everything that is there — it links to it and explains *how to work with the codebase* day-to-day.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Layout](#2-repository-layout)
3. [Development Environment Setup](#3-development-environment-setup)
4. [Running the Stack](#4-running-the-stack)
5. [Architecture — What You Must Know](#5-architecture--what-you-must-know)
6. [Dev Policies, Rules, and Conventions](#6-dev-policies-rules-and-conventions)
7. [Backend — Adding a New Module](#7-backend--adding-a-new-module)
8. [Backend — Adding an Adapter](#8-backend--adding-an-adapter)
9. [Backend — Adding an API Route](#9-backend--adding-an-api-route)
10. [Frontend — Adding a New Page](#10-frontend--adding-a-new-page)
11. [Frontend — Adding a Reusable Component](#11-frontend--adding-a-reusable-component)
12. [Writing Tests](#12-writing-tests)
13. [Event-Driven Pipeline — How It Fits Together](#13-event-driven-pipeline--how-it-fits-together)
14. [Domain Configuration](#14-domain-configuration)
15. [Commit and PR Workflow](#15-commit-and-pr-workflow)
16. [Common Problems and How to Fix Them](#16-common-problems-and-how-to-fix-them)

---

## 1. Project Overview

**chiliAI** is a **domain-reconfigurable Graph RAG analytics platform**. It combines knowledge-graph construction, vector-based retrieval-augmented generation (RAG), graph neural networks, time-series anomaly detection, risk scoring, and explainable AI into one loosely coupled system operated through a browser-based analyst workbench.

The starting exemplar domain is **Medicare fraud detection**, but the platform is designed so that changing a single YAML configuration file retargets the entire system to a different investigation domain (food supply chain, financial crime, etc.) with no code changes.

### What makes this platform different from a generic RAG system

1. **Graph-native** — RAG results are enriched with subgraph patterns and neighbourhood context from a knowledge graph, not just vector-similarity chunks.
2. **Multi-signal analytics** — time-series anomaly detection, GNN link prediction, and risk scoring run as a feedback loop; each round enriches the graph for the next.
3. **Fully vendor-agnostic** — every external system (graph DB, vector store, LLM, object store, embedding model) is behind an abstract protocol. Swapping vendors is an adapter change, not an application change.
4. **Domain-reconfigurable** — entity types, relationship types, display labels, enabled capabilities, and alert thresholds are driven from a YAML config file that is hot-loadable at startup.

### Current state

The codebase is an **active local-development prototype** with substantial backend and frontend implementation. The backend includes the FastAPI gateway, worker/coordinator, Redis event pipeline, ingestion, graph/vector/embedding/LLM/RAG services, analytics, monitoring, storage adapters, auth/RBAC middleware, CI, and Kubernetes/Helm manifests. The frontend is a routed analyst workbench with Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, RAG Chat, and Configuration views. Most `TODO(production)` annotations now mark hardening or deeper production features rather than blank-module scaffolding.

---

## 2. Repository Layout

```
chiliAI/
├── backend/            Python 3.12 — FastAPI API gateway, pipeline workers, analytics
├── chili_app/          React 19 + TypeScript + Vite 8 — analyst workbench SPA
├── docs/               Architecture, design docs, active audits, and archived planning material
│   └── archive/
│       └── planning/   Historical backlog/story prompts, retained for reference only
├── infra/              Docker Compose configs, Kubernetes manifests, Helm chart
├── Makefile            Top-level dev commands (make dev, make test, etc.)
├── docker-compose.dev.yaml   Development stack (hot-reload mounts)
├── docker-compose.yaml       Production stack (built images, nginx)
└── .github/
    ├── copilot-instructions.md  Project rules for AI coding agents
    └── instructions/
        └── backend.instructions.md  Backend-specific rules
```

Key documentation files:

| File | Purpose |
|------|---------|
| [`docs/architecture.md`](architecture.md) | Authoritative design document — read §1-§6 before writing any code |
| [`docs/onboarding.md`](onboarding.md) | This file |
| [`backend/README.md`](../backend/README.md) | Backend-specific setup and commands |
| [`chili_app/README.md`](../chili_app/README.md) | Frontend-specific setup and commands |

---

## 3. Development Environment Setup

### 3.1 Prerequisites

| Tool | Required version | Install |
|------|-----------------|---------|
| Docker Desktop | Latest stable | https://docs.docker.com/get-docker/ |
| Docker Compose | V2 (bundled with Docker Desktop) | — |
| Python | ≥ 3.12 | `brew install python@3.12` or https://python.org |
| Node.js | ≥ 20 | `brew install node` or https://nodejs.org |
| Git | Any recent | pre-installed on macOS |
| `gh` CLI | Latest | `brew install gh` |

The full stack (API, worker, Redis, Neo4j, Qdrant, MinIO) runs inside Docker, so Python and Node are only needed for local development without Docker (linters, type-checkers, running tests directly).

### 3.2 Clone and first run

```bash
# 1. Clone
git clone https://github.com/rhagan9202/chiliAI.git chiliAI
cd chiliAI

# 2. Create local environment file (gitignored)
cp .env.example .env           # edit if you need non-default API keys

# 3. Start the full dev stack (builds images, mounts source directories)
make dev
# or, equivalently:
# docker compose -f docker-compose.dev.yaml up --build
```

The first run will pull and build images; expect ~3–5 minutes. After that, incremental rebuilds are fast because Docker caches layers.

### 3.3 Backend — local Python setup (for linting, type-checking, running tests without Docker)

```bash
cd backend

# Create a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install the package in editable mode with all dev extras
pip install -e ".[dev]"

# Verify
python -c "import fastapi; print(fastapi.__version__)"
pyright --version
pytest --version
```

Installing optional adapter dependencies (only if you need to run adapter-specific code locally):

```bash
pip install -e ".[neo4j]"     # Neo4j driver
pip install -e ".[qdrant]"    # Qdrant client
```

### 3.4 Frontend — local Node setup

```bash
cd chili_app
npm install
```

---

## 4. Running the Stack

### 4.1 Docker Compose (recommended)

```bash
make dev          # Start full dev stack with hot-reload
make down         # Stop the stack (preserves volumes)
make clean        # Stop the stack AND wipe volumes (fresh state)
make logs         # Tail all container logs
make api-shell    # Drop into a bash shell inside the API container
make test         # Run backend pytest suite inside the API container
```

All service URLs when the dev stack is running:

| Service | URL |
|---------|-----|
| Frontend (Vite HMR) | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API health | http://localhost:8000/health |
| OpenAPI docs (Swagger) | http://localhost:8000/docs |
| OpenAPI docs (ReDoc) | http://localhost:8000/redoc |
| Neo4j browser | http://localhost:7474 |
| Qdrant dashboard | http://localhost:6333/dashboard |
| MinIO console | http://localhost:9001 (admin: `minioadmin` / `minioadmin`) |
| Redis | localhost:6379 (no browser UI; use `redis-cli`) |

Dev-stack notes:

- The dev stack starts Neo4j with `NEO4J_AUTH=none`, while the production compose file uses `NEO4J_AUTH=${NEO4J_USER}/${NEO4J_PASSWORD}`. When a domain config selects `graph.backend: neo4j`, the API/worker use `graph.auth_env_var` if configured; otherwise they fall back to `NEO4J_USER`/`NEO4J_PASSWORD`. Keep those values aligned with the Neo4j service on fresh machines.
- The API container uses explicit Uvicorn `--reload-dir` entries for backend source packages and keeps mutable runtime data such as `/app/data` outside the watch set. Do not revert dev compose to a bare repository-wide reload watcher; runtime artifact writes can otherwise trigger reload loops.
- Uvicorn excludes common generated/cache paths (`*.pyc`, `__pycache__/*`, `*.egg-info/*`) from reload watches.
- API and worker Redis Streams polling defaults to `CHILI_EVENT_BLOCK_MS=500` in dev compose to reduce idle wakeups while preserving responsive local event handling.
- The browser opens `/events/stream` for realtime workspace status. This SSE heartbeat intentionally reads cached API projections only and must not perform live graph metric recomputation; use the KB list/detail APIs for explicit graph-backed projection refreshes.
- `make dev` attaches to Docker Compose logs. In the interactive Compose log UI, press `d` to detach while leaving containers running.
- Browser tests or manual Playwright checks should avoid waiting for `networkidle` on pages that open `/events/stream`; the SSE connection is intentionally long-lived.

### 4.2 Running services individually (without Docker)

You will need Redis, Neo4j, Qdrant, and MinIO running separately. The easiest way is to start just the infrastructure containers:

```bash
# Start only the infrastructure services
docker compose -f docker-compose.dev.yaml up redis neo4j qdrant minio
```

Then in separate terminals:

```bash
# API server
cd backend
source .venv/bin/activate
CHILI_CONFIG_PATH=config/defaults/medicare_fraud.yaml \
REDIS_URL=redis://localhost:6379 \
NEO4J_URI=bolt://localhost:7687 \
QDRANT_URL=http://localhost:6333 \
MINIO_ENDPOINT=localhost:9000 \
MINIO_ACCESS_KEY=minioadmin \
MINIO_SECRET_KEY=minioadmin \
uvicorn api.app:create_app --factory --reload --port 8000
```

```bash
# Pipeline worker
cd backend
source .venv/bin/activate
CHILI_CONFIG_PATH=config/defaults/medicare_fraud.yaml \
REDIS_URL=redis://localhost:6379 \
python -m agent.coordinator
```

```bash
# Frontend
cd chili_app
npm run dev
```

### 4.3 Environment variables

The key environment variables consumed by the backend:

| Variable | Default (dev) | Description |
|----------|---------------|-------------|
| `CHILI_CONFIG_PATH` | `/app/config/defaults/medicare_fraud.yaml` | Path to the active domain config YAML |
| `REDIS_URL` | `redis://redis:6379` | Redis connection string |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j Bolt URI |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant HTTP URL |
| `MINIO_ENDPOINT` | `minio:9000` | MinIO host:port |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `ALLOWED_ORIGINS` | localhost origins in dev | Comma-separated CORS origin list |
| `CHILI_EVENT_BLOCK_MS` | `500` in dev compose | Redis Streams blocking read timeout; increase to reduce idle wakeups, decrease only if local event latency requires it |
| `LOG_LEVEL` | `INFO` | Backend log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, or numeric level) |
| `LOG_FORMAT` | `console` | Backend log renderer; use `json` for structured log aggregation |

---

## 5. Architecture — What You Must Know

> Full details are in [`docs/architecture.md`](architecture.md). This section is a condensed mental model for day-to-day coding.

### 5.1 Three-container deployment

```
chili-app (React SPA)  →  chili-api (FastAPI)  ↔  chili-worker (pipeline runner)
                                      ↕
                                    Redis Streams
                        (all three read/write here)
```

The API never does long-running computation. It validates input, publishes events to Redis, and returns `202 Accepted`. Workers consume those events and do the real work.

### 5.2 Backend modules

```
backend/
  api/          FastAPI gateway — thin routing only, no business logic
  ingestion/    Document parsing, chunking, entity extraction
  records/      Structured/tabular ingestion (CSV / JSONL / API push) — raw_records landing
  graph/        Knowledge graph CRUD (in-memory / Neo4j; other adapters are roadmap)
  vectorstore/  Embedding storage and similarity search (in-memory / Qdrant; other adapters are roadmap)
  embeddings/   Text and graph-metric embedding generation
  rag/          RAG pipeline: embed query → search → expand graph → assemble context → LLM
  llm/          LLM client abstraction (OpenAI / Anthropic / Ollama)
  analytics/
    timeseries/ Time-series anomaly detection
    gnn/        Graph neural network link prediction and clustering
    risk/       Risk scoring engine
    explainability/ Evidence pack generation
  agent/        Workflow / pipeline coordinator (async state machine)
  monitoring/   Active monitoring: claim stream consumer, alert generation
  shared/       Domain types, cross-cutting protocols, small utilities — leaf dependency, no business logic
  config/       YAML/JSON domain config loading and validation
  events/       Redis Streams event bus abstraction
  storage/      Object/file storage abstraction (S3 / MinIO / local FS)
  database/     Postgres + TimescaleDB ConnectionProvider, Alembic migrations
```

### 5.3 Cross-module interaction rules (strictly enforced)

Feature modules **must not** import directly from each other. There are exactly three permitted interaction paths:

| Path | Mechanism | When to use |
|------|-----------|-------------|
| **A** | FastAPI router orchestrates multiple services through injected dependencies | Frontend-initiated synchronous actions |
| **B** | Agent coordinator publishes/consumes Redis Streams events | Multi-step pipelines |
| **C** | `shared/` package — types, protocols, utilities | Stable contracts shared across modules |

**Forbidden**: `analytics` importing from `ingestion`, `graph` importing from `api`, direct implementation coupling of any kind.

### 5.4 Every external system is behind a protocol

No business logic ever imports a vendor SDK (e.g., `neo4j`, `qdrant_client`, `openai`) directly. Vendor code lives exclusively in `adapters/` sub-packages. The rest of the codebase sees only the abstract protocol.

```
graph/
  protocols.py        ← defines GraphRepositoryProtocol (what the module needs)
  adapters/
    in_memory.py      ← fake adapter for tests
    neo4j_adapter.py  ← real Neo4j adapter
```

### 5.5 Generic domain model

There are **no hardcoded domain field names** in shared types. Entities flow through the system as:

```python
Entity(id="...", type="provider", properties={"npi": "...", "state": "..."})
```

The `type` and `properties` keys are defined by the active domain configuration YAML. The `shared/types.py` file defines generic containers like `Entity`, `Relationship`, `Alert`, and `EvidencePack` — never `Provider`, `Beneficiary`, or `Claim` as concrete classes.

---

## 6. Dev Policies, Rules, and Conventions

### 6.1 Backend

| Rule | Detail |
|------|--------|
| **Python version** | 3.12. Use its syntax and stdlib features freely. |
| **Type checking** | All code must pass `pyright --strict`. Full annotations, no untyped `Any`, explicit domain types. |
| **Test coverage** | ≥ 85% per package for any code you add or change. Missing tests = incomplete work. |
| **Test isolation** | Mock or fake external systems at the adapter boundary. Unit tests must not need a live database, Redis, or LLM. |
| **No business logic in routers** | `api/routers/*.py` must only validate input, call service methods, and return responses. |
| **No cross-module imports** | Each module only touches `shared/`, its own internals, and injected protocol dependencies. |
| **Protocol-first** | Define the protocol in `protocols.py` before writing the implementation. |
| **Adapters stay isolated** | Vendor SDK imports live only inside `adapters/`. |
| **Linting** | `ruff` is the linter/formatter. Code must be clean before commit. |

Run checks locally:

```bash
cd backend
source .venv/bin/activate
pyright                       # strict type check
ruff check .                  # lint
ruff format .                 # format
pytest --cov --cov-report=term-missing   # tests with coverage report
```

### 6.2 Frontend

| Rule | Detail |
|------|--------|
| **TypeScript strict mode** | `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch` — the build will fail if these are violated. |
| **Functional components only** | No class components. React hooks for all stateful logic. |
| **Server state** | TanStack Query for all API data fetching, caching, and mutation. |
| **Client state** | Zustand for UI-only state (selected entity, panel visibility, filters). |
| **Routing** | React Router v7. |
| **No business logic in components** | Extract fetch logic into TanStack Query hooks in `api/hooks/`. |
| **Lint** | `npm run lint` must pass before committing. |
| **Build** | `npm run build` must succeed (TypeScript compile + Vite bundle). |

Run checks locally:

```bash
cd chili_app
npm run lint
npm run build
```

### 6.3 General

- **Tests are not optional.** Backend changes that lack test coverage are treated as incomplete regardless of how the feature appears to work.
- **No console.log / print in production code.** Use `structlog` (backend) and proper React error boundaries / Sentry (frontend) instead.
- **Secrets never in source.** No API keys, passwords, or credentials in code or committed config. Use environment variables.
- **Update docs when you change architecture.** If you add a command, change environment variable names, or make a new architectural decision, update `docs/architecture.md` and relevant READMEs in the same PR.
- **Design docs** — significant decisions (new dependency, changed module boundaries, new event type) should be documented in `docs/architecture.md`, the relevant README, or a new dated design note under `docs/`.
- **Archived planning** — historical story prompts and backlog files live under `docs/archive/planning/`. Treat them as reference material, not live acceptance criteria.

---

## 7. Backend — Adding a New Module

Use this when a new capability is too substantial to go inside an existing module and warrants its own clear boundary.

### 7.1 Create the package structure

```bash
mkdir -p backend/mymodule/adapters
touch backend/mymodule/__init__.py
touch backend/mymodule/protocols.py
touch backend/mymodule/models.py
touch backend/mymodule/service_models.py
touch backend/mymodule/service.py
touch backend/mymodule/exceptions.py
touch backend/mymodule/adapters/__init__.py
touch backend/mymodule/adapters/in_memory.py
mkdir -p backend/tests/mymodule
touch backend/tests/mymodule/__init__.py
touch backend/tests/mymodule/test_service.py
```

### 7.2 Define the protocol first (`protocols.py`)

```python
"""Service-level protocols for the mymodule module."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from mymodule.service_models import MyInput, MyOutput


@runtime_checkable
class MyServiceProtocol(Protocol):
    """Public contract for mymodule. Depend on this, not the concrete service."""

    def process(self, input: MyInput) -> MyOutput: ...


__all__ = ["MyServiceProtocol"]
```

Rules:
- `runtime_checkable` so the protocol can be used in `isinstance()` checks for adapter validation.
- All methods fully annotated — no `Any`.
- Only types from `shared/` or the module's own `service_models.py` appear in the signature.

### 7.3 Define service models (`service_models.py`)

Request/response types that cross the service boundary. Use Pydantic `BaseModel` for everything that crosses a module boundary.

```python
from __future__ import annotations
from pydantic import BaseModel


class MyInput(BaseModel):
    entity_id: str
    options: dict[str, str] = {}


class MyOutput(BaseModel):
    result: str
    confidence: float
```

### 7.4 Implement the service (`service.py`)

```python
from __future__ import annotations

from mymodule.protocols import MyServiceProtocol
from mymodule.service_models import MyInput, MyOutput
from mymodule.exceptions import MyModuleError


class MyService:
    """Concrete implementation of MyServiceProtocol."""

    def __init__(self, dependency: SomeDependencyProtocol) -> None:
        self._dep = dependency

    def process(self, input: MyInput) -> MyOutput:
        # business logic here
        ...


# Type assertion — caught by pyright if the class drifts from the protocol
_: MyServiceProtocol = MyService.__new__(MyService)
```

### 7.5 Write the in-memory adapter (`adapters/in_memory.py`)

Every module that needs an external resource must have a fake/in-memory adapter usable in tests without any real infrastructure.

```python
from __future__ import annotations
from mymodule.protocols import MyServiceProtocol
from mymodule.service_models import MyInput, MyOutput


class InMemoryMyService:
    """Fake implementation for unit tests."""

    def __init__(self) -> None:
        self._calls: list[MyInput] = []

    def process(self, input: MyInput) -> MyOutput:
        self._calls.append(input)
        return MyOutput(result="fake", confidence=1.0)


_: MyServiceProtocol = InMemoryMyService.__new__(InMemoryMyService)
```

### 7.6 Register the module in `pyproject.toml`

Add your package to the `find` list so it is installed with the project:

```toml
[tool.setuptools.packages.find]
include = ["api*", "agent*", ..., "mymodule*"]
```

### 7.7 Wire into the FastAPI dependency injection

In `backend/api/dependencies.py`, add a factory for your service so it can be injected into routers:

```python
from functools import lru_cache
from mymodule.service import MyService
from mymodule.protocols import MyServiceProtocol

@lru_cache
def get_my_service() -> MyServiceProtocol:
    # wire in the real adapter, reading config from environment
    return MyService(dependency=...)
```

---

## 8. Backend — Adding an Adapter

Adapters plug a concrete vendor/library implementation behind an existing abstract protocol.

### 8.1 Pattern

Every module that touches an external system has:

```
mymodule/
  protocols.py           ← defines MyRepositoryProtocol (what the module needs from the world)
  adapters/
    in_memory.py         ← fake — for unit tests
    vendor_a.py          ← real implementation A
    vendor_b.py          ← real implementation B
```

### 8.2 Example: Adding a future graph adapter

Suppose you are adding a Memgraph adapter to the existing `graph/` module. Memgraph is a roadmap backend, not a currently selectable `DomainConfig.graph.backend` value. A new adapter is complete only after its protocol implementation, tests, dependency extra, DI factory branch, and config literal are all updated together.

1. **Implement the protocol** in `backend/graph/adapters/memgraph_adapter.py`:

```python
"""Memgraph adapter for GraphRepositoryProtocol."""
from __future__ import annotations

from graph.protocols import GraphRepositoryProtocol
# import Memgraph driver ONLY here — never in business logic
from neo4j import GraphDatabase  # memgraph is wire-compatible with the Neo4j driver


class MemgraphGraphRepository:
    """GraphRepositoryProtocol backed by Memgraph via the Bolt protocol."""

    def __init__(self, uri: str, auth: tuple[str, str]) -> None:
        self._driver = GraphDatabase.driver(uri, auth=auth)

    def upsert_entity(self, kb_id: str, entity: Entity) -> None:
        with self._driver.session() as session:
            session.run(
                "MERGE (n {id: $id, kb_id: $kb_id}) SET n += $props",
                id=entity.id,
                kb_id=kb_id,
                props=entity.properties,
            )

    # ... implement all other protocol methods


# Pyright protocol conformance check
_: GraphRepositoryProtocol = MemgraphGraphRepository.__new__(MemgraphGraphRepository)
```

2. **Keep the vendor import inside the adapter file.** The only place `from neo4j import ...` (or `from qdrant_client import ...`, `from openai import ...`, etc.) should appear is inside an `adapters/` file.

3. **Add any new dependency to `pyproject.toml`** under the appropriate optional extras group:

```toml
[project.optional-dependencies]
memgraph = ["neo4j>=5,<6"]   # Memgraph uses the same driver
```

4. **Wire selection explicitly.** Update `backend/config/schema.py` to include the new literal and update the dependency factory to construct the adapter. Do not advertise a backend in config until that branch exists.

5. **Write tests** using the in-memory adapter. Integration tests that require an actual Memgraph instance should be marked `@pytest.mark.integration` and excluded from the default test run.

---

## 9. Backend — Adding an API Route

### 9.1 Rules

- **Routers are thin.** They validate input (Pydantic models), call service methods through injected dependencies, and return responses. No business logic.
- **No direct imports from service internals.** Routers inject the _protocol_ type from `Depends()`, not the concrete class.
- **Async handlers** where the underlying operation is I/O-bound (database call, LLM call, Redis publish). Use `async def` and `await`.

### 9.2 Example: Adding an endpoint to an existing router

Say you are adding `GET /knowledgebases/{kb_id}/stats` to `api/routers/knowledgebases.py`:

```python
# backend/api/routers/knowledgebases.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_graph_service
from graph.protocols import GraphServiceProtocol

router = APIRouter(prefix="/knowledgebases", tags=["knowledgebases"])


class KBStatsResponse(BaseModel):
    entity_count: int
    relationship_count: int
    document_count: int


@router.get("/{kb_id}/stats", response_model=KBStatsResponse)
async def get_kb_stats(
    kb_id: str,
    graph_svc: GraphServiceProtocol = Depends(get_graph_service),
) -> KBStatsResponse:
    metrics = graph_svc.compute_metrics(kb_id)
    return KBStatsResponse(
        entity_count=metrics.entity_count,
        relationship_count=metrics.relationship_count,
        document_count=metrics.document_count,
    )
```

### 9.3 Adding a new router

1. Create `backend/api/routers/myrouter.py` following the pattern above.
2. Register it in `backend/api/app.py`:

```python
from api.routers import myrouter

def create_app() -> FastAPI:
    app = FastAPI(...)
    app.include_router(myrouter.router)
    return app
```

### 9.4 Request/response models

- Define response models as Pydantic `BaseModel` classes in the router file or in a dedicated `api/schemas/` file if they are reused across routers.
- Never expose internal service models directly as API responses — define an explicit response shape. This gives you freedom to evolve the internal model without breaking the API contract.

---

## 10. Frontend — Adding a New Page

The frontend lives at `chili_app/src/` and already has the main workbench pages, layout, stores, hooks, and components. For new pages, follow the current flat page-file pattern from [`docs/architecture.md §8`](architecture.md#8-frontend-architecture):

```
chili_app/src/
  pages/
    Dashboard.tsx
    KnowledgeBaseManager.tsx
    AlertFeed.tsx
    InvestigationWorkbench.tsx
    RagChat.tsx
    ConfigEditor.tsx
```

### 10.1 Create the page component

```bash
touch chili_app/src/pages/MyPage.tsx
```

`MyPage.tsx`:

```tsx
// chili_app/src/pages/MyPage.tsx
import { useMyData } from '../hooks/useMyData'

export function MyPage() {
  const { data, isLoading, error } = useMyData()

  if (isLoading) return <div>Loading...</div>
  if (error) return <div>Error: {error.message}</div>

  return (
    <main>
      <h1>My Page</h1>
      {/* render data */}
    </main>
  )
}
```

### 10.2 Add the TanStack Query hook

API data fetching goes in `chili_app/src/hooks/` and should use the shared `apiRequest` helper from `chili_app/src/lib/apiClient.ts`:

```ts
// chili_app/src/hooks/useMyData.ts
import { useQuery } from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'

interface MyData {
  id: string
  value: string
}

async function fetchMyData(): Promise<MyData[]> {
  return apiRequest<MyData[]>('/my-endpoint')
}

export function useMyData() {
  return useQuery({ queryKey: ['myData'], queryFn: fetchMyData })
}
```

### 10.3 Register the route

Add the route in `chili_app/src/App.tsx` (or wherever the route config lives):

```tsx
import { MyPage } from './pages/MyPage'

// Inside the router config:
<Route path="/my-page" element={<MyPage />} />
```

### 10.4 TypeScript rules for pages

- Explicitly type all props and state — do not rely on inferred `any`.
- No unused imports or variables (the build will fail).
- No `switch` fallthrough.

---

## 11. Frontend — Adding a Reusable Component

Components that are used in more than one page go in `chili_app/src/components/`.

### 11.1 Component categories

| Directory | Purpose |
|-----------|---------|
| `components/investigation/` | Graph canvas, entity detail, evidence, timeline |
| `components/alerts/` | Alert list item, alert badge, alert detail |
| `components/chat/` | RAG chat message list and input |
| `components/knowledgebase/` | KB tables, detail view, upload widgets |
| `components/common/` | Shared primitives — layout, loading spinner, error boundary |

### 11.2 Component template

```tsx
// chili_app/src/components/common/StatusBadge.tsx
interface StatusBadgeProps {
  status: 'ok' | 'warning' | 'error'
  label: string
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const colors: Record<StatusBadgeProps['status'], string> = {
    ok: 'green',
    warning: 'amber',
    error: 'red',
  }

  return (
    <span style={{ color: colors[status] }}>
      {label}
    </span>
  )
}
```

### 11.3 Domain-aware components

Many components need to render labels driven by the domain configuration rather than hardcoded strings. Read the domain config through `useDomainConfig()`:

```ts
import { useDomainConfig } from '../../hooks/useDomainConfig'

export function EntityTypeBadge({ entityType }: { entityType: string }) {
  const { config } = useDomainConfig()
  const def = config.entities.find((e) => e.name === entityType)
  return <span>{def?.display_label ?? entityType}</span>
}
```

---

## 12. Writing Tests

### 12.1 Backend test structure

Tests live in `backend/tests/` and mirror the module structure:

```
backend/tests/
  graph/
    test_service.py
    test_in_memory_adapter.py
  ingestion/
    test_extractor.py
    test_chunker.py
  shared/
    test_types.py
  ...
```

### 12.2 Unit test pattern

```python
# backend/tests/graph/test_service.py
import pytest
from graph.adapters.in_memory import InMemoryGraphRepository
from graph.service import GraphService
from graph.service_models import GraphBuildTask
from shared.types import Entity


@pytest.fixture
def service() -> GraphService:
    repo = InMemoryGraphRepository()
    return GraphService(repository=repo)


def test_upsert_and_retrieve_entity(service: GraphService) -> None:
    entity = Entity(id="e1", type="provider", properties={"npi": "1234567890"})
    task = GraphBuildTask(knowledge_base_id="kb1", entities=[entity], relationships=[])

    service.upsert_task(task)

    retrieved = service.get_entity(knowledge_base_id="kb1", entity_id="e1")
    assert retrieved is not None
    assert retrieved.id == "e1"
    assert retrieved.properties["npi"] == "1234567890"
```

### 12.3 Integration tests

Tests that require real infrastructure are marked with the `integration` pytest marker and skipped in the default run:

```python
import pytest

@pytest.mark.integration
def test_neo4j_upsert_entity(neo4j_uri: str) -> None:
    ...
```

Run integration tests explicitly:

```bash
pytest -m integration
```

### 12.4 Coverage requirements

```bash
# Check coverage for a specific package
pytest tests/graph/ --cov=graph --cov-report=term-missing

# Required: ≥ 85% for any package you touch
```

If you are adding a new module with complex logic, aim for 90%+ on the first pass; maintaining 85% is much easier than recovering from 60%.

### 12.5 Frontend tests

The frontend test suite uses Vitest with React Testing Library. Add tests under `src/**/__tests__/` for stores, hooks, pages, and reusable components. Mock API calls — do not make real HTTP calls in component tests.

```bash
cd chili_app
npm run test:run
```

---

## 13. Event-Driven Pipeline — How It Fits Together

Understanding the event pipeline is essential for any work touching ingestion, analytics, or the worker process.

### 13.1 Event flow overview

```
API receives request
  → publishes event to Redis Stream (via events.runtime)
  → returns 202 Accepted

Worker (agent/coordinator.py)
  → XREADGROUP from Redis Stream
  → dispatches to the appropriate pipeline step handler
  → step publishes downstream events
  → loop continues
```

### 13.2 Event types (`events/types.py`)

Events are typed Pydantic models defined in `events/types.py`. Each event has a `stream` key (where it lives in Redis) and a `type` discriminator.

When you add a new pipeline stage, define its input and output events here first.

### 13.3 Publishing an event from the API

```python
from events.runtime import EventRuntime
from events.types import DocumentUploadedEvent

async def upload_document(
    kb_id: str,
    content: bytes,
    event_runtime: EventRuntime = Depends(get_event_runtime),
) -> None:
    # ... save to object store ...
    await event_runtime.publish(
        DocumentUploadedEvent(knowledge_base_id=kb_id, document_id=doc_id)
    )
```

### 13.4 Consuming an event in the worker

```python
# agent/coordinator.py — simplified
from events.runtime import EventRuntime

async def run() -> None:
    async for event in runtime.consume(group="workers", consumer="worker-1"):
        match event:
            case DocumentUploadedEvent():
                await ingestion_step.run(event)
            case EntitiesExtractedEvent():
                await graph_step.run(event)
            case _:
                logger.warning("unhandled event type", event=event)
```

### 13.5 Adding a new pipeline event

1. Define the event type in `backend/events/types.py`.
2. Register the codec in `backend/events/codec.py` (until auto-discovery is implemented — story #152).
3. Publish from the appropriate service.
4. Add a handler branch in `agent/coordinator.py`.
5. Write tests for the new handler using the in-memory event bus adapter.

---

## 14. Domain Configuration

### 14.1 Where to find it

Default configs live at `backend/config/defaults/`. The active config is selected by the `CHILI_CONFIG_PATH` environment variable.

```
backend/config/defaults/
  medicare_fraud.yaml
  food_supply_chain.yaml   (example — may be partial)
```

### 14.2 Adding a new domain

1. Create `backend/config/defaults/my_domain.yaml` using the schema in [`docs/architecture.md §9`](architecture.md#9-domain-configuration-model).
2. Define `entities`, `relationships`, `capabilities`, `ingestion.sources`, and `alerts.thresholds`.
3. Set `CHILI_CONFIG_PATH` to point to your new file.
4. Restart the backend. The frontend reads `GET /config/domain` on startup and renders entity labels, icons, and feature gates driven by the config.

### 14.3 Accessing config in a backend module

```python
from config.loader import get_domain_config
from config.schema import DomainConfig

# At module init (via DI):
config: DomainConfig = get_domain_config()
entity_types = {e.name for e in config.entities}
```

Never hardcode entity type strings like `"provider"` in business logic. Always compare against the config.

---

## 15. Commit and PR Workflow

### 15.1 Branch naming

```
feature/<story-id>-short-description     # new feature: feature/E14-S02-hybrid-embedding
fix/<issue-number>-short-description     # bug fix:     fix/137-embedding-service-crash
chore/<description>                      # housekeeping: chore/update-gitignore
docs/<description>                       # docs only:    docs/onboarding-guide
```

### 15.2 Commit messages

Follow the Conventional Commits format:

```
<type>(<scope>): <short summary>

[optional body]

[optional footer: closes #issue]
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`

Examples:
```
feat(embeddings): add graph-metric hybrid embedding flow (E14-S02)
fix(rag): handle empty context retrieval without raising KeyError
test(graph): add in-memory adapter coverage to 92%
docs(onboarding): add section on adding adapters
```

### 15.3 PR checklist

Before opening a PR:

- [ ] `pyright` passes (backend)
- [ ] `ruff check .` passes (backend)
- [ ] `pytest --cov` passes with ≥ 85% coverage for touched packages
- [ ] `npm run lint` passes (frontend, if changed)
- [ ] `npm run build` succeeds (frontend, if changed)
- [ ] New module or endpoint has corresponding tests
- [ ] `docs/architecture.md` updated if architecture has changed
- [ ] Story acceptance criteria in the SP prompt are all satisfied

### 15.4 Creating and tracking GitHub Issues

```bash
# Check existing issues
gh issue list --repo rhagan9202/chiliAI

# Create an issue from an archived story prompt, if it is still relevant
gh issue create \
  --repo rhagan9202/chiliAI \
  --title "Story E14-S02: EmbeddingsService — graph-metric hybrid embedding flow" \
  --body-file docs/archive/planning/story_prompts/SP_E14_S02_prompt.md

# Link a PR to an issue (in PR body)
Closes #137
```

The script `.tmp/create_story_issues_batch.py` automates bulk issue creation from story prompts and skips any that already exist.

---

## 16. Common Problems and How to Fix Them

### `pyright` reports errors about `Any` or missing annotations

Check that all function parameters and return types are explicitly annotated. `pyright --strict` does not allow implicit `Any` anywhere. If you are accepting a value whose type is genuinely unknown at the protocol boundary, define a constrained type or a `TypeVar`.

### Tests fail with `ModuleNotFoundError`

Make sure you installed the package in editable mode: `pip install -e ".[dev]"`. If you added a new package, check that it is listed in `pyproject.toml` under `[tool.setuptools.packages.find]`.

### `make dev` fails because a port is already in use

Check for processes already running on ports 5173, 8000, 6379, 7474, or 6333:

```bash
lsof -i :8000      # find what is using port 8000
kill -9 <PID>
```

Or change the port mapping in `docker-compose.dev.yaml`.

### Redis connection refused (running locally without Docker)

Make sure the Redis container or a local Redis instance is running:

```bash
docker compose -f docker-compose.dev.yaml up redis   # start just Redis
redis-cli ping                                        # should return PONG
```

### Neo4j health check fails on first `make dev`

Neo4j can take 30–60 seconds on a cold start. Docker Compose will retry the health check up to 5 times with a 15-second interval. Wait for the `neo4j` container to show `healthy` in `make logs` before worrying.

### Frontend TypeScript build fails with `noUnusedLocals` error

Remove the unused import or variable. TypeScript strict mode treats these as errors, not warnings. VS Code will highlight them in the editor before you run the build.

### Protocol conformance check fails at runtime

If you see a `TypeError` like `Expected X to implement protocol Y`, it usually means an adapter class is missing one or more methods required by the protocol. Check the protocol definition in `protocols.py` and make sure all methods are implemented with matching signatures.

### Coverage falls below 85%

Run `pytest --cov=mymodule --cov-report=term-missing` to see exactly which lines are not covered. Common causes:
- Error branches that need a test for the failure path
- New public methods added to a service without corresponding test cases
- Adapter-specific code that needs an integration test or a fake test

---

*Last updated: April 2026. For questions, open a GitHub Issue or Discussion in the repo.*
