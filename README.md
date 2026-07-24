# chiliAI

[![CI](https://github.com/rhagan9202/chiliAI/actions/workflows/ci.yml/badge.svg?branch=prod)](https://github.com/rhagan9202/chiliAI/actions/workflows/ci.yml)

A **domain-reconfigurable Graph RAG analytics platform**. Combines knowledge-graph construction, vector-based retrieval-augmented generation, graph neural networks, time-series analysis, anomaly detection, and explainable AI in a loosely coupled, modular system operated through a browser-based analyst workbench.

> For the full architecture and design, see [`docs/architecture.md`](docs/architecture.md).

---

## Goals

- **Flexible, reconfigurable platform** — built around Graph RAG for analytics/exploration, ML, GNN, explainable AI, time-series analysis, and anomaly detection through loosely coupled, interchangeable capability modules in a Python 3.12 backend.
- **Domain reconfigurability** — a single YAML/JSON configuration surface (or UI wizard) retargets the platform to different domains (entity names, relationships, display labels, enabled capabilities). Examples: Medicare fraud detection, food supply chain monitoring, financial crime.
- **Vendor-agnostic boundaries** — external systems are accessed through abstract interface contracts. Currently selectable backends are graph (in-memory, Neo4j), vector store (in-memory, Qdrant), LLM (local, OpenAI, Anthropic, Ollama), embeddings (local, OpenAI, sentence-transformers), and object storage (local FS, S3/MinIO-compatible). Memgraph, Neptune, pgvector, Weaviate, GCS, and vLLM are roadmap adapters.

## Demo: Tennessee Medicare Subset

A self-contained end-to-end demo uses a Tennessee-provider subset of the publicly available NPPES and CMS DE-SynPUF datasets. The demo builds a knowledge base, ingests the records-derived entities into the graph + vector store, and then uploads a synthetic policy-document corpus (Markdown/HTML/JSON/TXT/DOCX under `backend/tests/ingestion/fixtures/policies/`) through the document endpoint so the configured LLM extractor produces a policy graph (`policy`/`procedure_code`/`regulation_section`) that joins the records graph on the shared `provider` node — all with one Make target.

```bash
CMS_DOWNLOADS_DIR=/path/to/downloads make data-setup   # one-time: stage the CMS/NPPES source data (gitignored, GB-scale)
make dev                                                # bring up the full stack, wait for healthy
make demo-tn-subset                                     # build TN subset + create KB + upload records + policy corpus
```

> **Data:** the demo needs the public CMS DE-SynPUF + NPPES source files staged locally first. **[`docs/testing/DATA.md`](docs/testing/DATA.md) is the single source of truth** for where all test/sample data lives, the fixture index, and how to stage the bulk data. `sample_data/` is gitignored — never commit bulk data.

The policy corpus upload is best-effort: set `DEMO_SKIP_POLICIES=1` to skip it, or `DEMO_POLICIES_DIR=...` to point at a different corpus. (PDF fixtures are a documented follow-up — see `docs/superpowers/specs/notes/synthetic-policy-corpus.md`.)

See [`docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md`](docs/superpowers/specs/2026-05-22-ingestion-pipeline-e2e-demo-design.md) for the full specification.

`make demo-cms` (`scripts/demo_cms.sh`) wraps this into one orchestrated bring-up for the CMS fraud walkthrough (BL-051): it requires the stack already running (`make dev`; it never composes up itself), switches the active pack to `medicare_fraud_cms_desynpuf` (never the generic `medicare_fraud` pack — no storage pins), stages/builds the TN subset if needed, runs the ingest above, then polls the alerts/GNN-clusters/evidence-pack/policy-items endpoints until the demo is analytics-ready, printing the KB id, probe counts, and the workbench URLs to walk through (`/alerts`, `/investigation/<entity>?kb=<kb>`, `/dashboard`, `/policy`, `/rag-chat`).

## Starting Exemplar: Medicare Fraud Detection

### Phase 1 — Build the policy knowledge base (batch)

1. Ingest policy documents (PDF, DOCX, HTML, JSON, TXT)
2. Extract entities, relationships, and metadata → build the policy knowledge graph
3. Embed and index extracted text and graph metrics into a vector store for RAG retrieval

The analyst can view a summary of ingested documents, add or remove documents, and delete or create knowledge bases. RAG index rebuild controls are planned but not wired in the current API/UI.

### Phase 2 — Active monitoring (streaming + batch)

4. Ingest structured and unstructured data — claims records, beneficiary information, provider data, medical records
5. Normalize, chunk, and extract entities → create/update the claims knowledge graph
6. Run analytics pipeline — time-series anomaly detection, GNN link prediction and clustering, risk scoring. Results feed back into the knowledge graph (self-reinforcing loop) and forward to the analyst workbench.
7. Surface alerts with evidence/explainability packs (reasoning, subgraph patterns, confidence scores)
8. Analyst explores and queries the graph for investigation
9. Analyst interacts with the knowledge base via the RAG chat interface. The current API path persists conversations and calls the configured RAG service; direct `ApiState()` test construction still has a deterministic in-memory fallback.

## Repository Structure

```
chiliAI/
├── backend/        # Python 3.12 backend — FastAPI gateway, workers, analytics modules
├── chili_app/      # React 19 + TypeScript + Vite 8 frontend — analyst workbench SPA
├── docs/           # Architecture, design documents, ADRs
├── infra/          # Deployment configuration (Docker Compose, Kubernetes, Helm)
└── .github/        # CI/CD workflows, Copilot instructions
```

## Quick Start

### Docker (Recommended)

```bash
# Development — full stack with hot-reload
cp .env.example .env          # create local config (gitignored; includes CHILI_ENV=local)
make dev                       # or: docker compose -f docker-compose.dev.yaml up --build

# Optional live graph smoke after the dev stack is healthy
bash scripts/smoke_graph_workflow.sh

# Production — built images, nginx, no hot-reload
make prod                      # or: docker compose up --build -d
```

The development Compose stack wires API and worker through Redis Streams, shared local filesystem object storage, and Neo4j graph persistence via `backend/config/defaults/medicare_fraud_cms_desynpuf.yaml` (the default pack for `make dev`/`make prod`; see `backend/config/README.md` for the full pack list and the `CHILI_CONFIG_OVERLAY_PATH` environment-overlay mechanism). The smoke script creates a temporary KB, uploads a Medicare-domain JSON document, waits for the graph pipeline, validates Investigation search/detail/neighborhood APIs, and prints an Investigation route containing a real generated entity ID.

| Service | Dev URL | Prod URL |
|---------|---------|----------|
| Frontend (Vite / nginx) | http://localhost:5173 | http://localhost |
| Backend API | http://localhost:8000 | http://localhost/api/ |
| API health check | http://localhost:8000/health | http://localhost/api/health |
| Neo4j browser | http://localhost:7474 | http://localhost:7474 |
| Qdrant dashboard | http://localhost:6333/dashboard | http://localhost:6333/dashboard |
| MinIO console | http://localhost:9001 | http://localhost:9001 |

See `make help` for all available commands.

### Prerequisites

- Python ≥ 3.12
- Node.js ≥ 20
- Redis 7+ (for event streaming)
- A graph database (Neo4j 5 recommended for local dev)

### Frontend

```bash
cd chili_app
npm install
npm run dev       # Vite dev server on http://localhost:5173
npm run build     # Production build
npm run lint      # ESLint check
```

### API Contract Codegen

Backend OpenAPI is the source of truth for frontend API DTOs.

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
```

Commit both `chili_app/openapi.json` and `chili_app/src/lib/api/schema.ts` when backend API contracts change.

### Backend

```bash
cd backend
# Create and activate a virtual environment (uv manages Python envs), then:
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"
CHILI_ENV=local uvicorn api.app:create_app --factory --reload --port 8000   # API server
python -m agent.coordinator                         # Pipeline worker
pytest --cov                                        # Run tests with coverage
```

> **Current state**: chiliAI is an active local-development prototype. The backend includes the FastAPI gateway, domain config, event bus, ingestion, graph, vector, embeddings, LLM, RAG, analytics, monitoring, storage, auth/RBAC middleware, config-driven adapter selection, CI, and worker orchestration with extensive tests. The frontend includes a routed analyst workbench shell with Dashboard, Knowledge Base Manager, Alert Feed, Investigation Workbench, Case Management, Policy Intelligence, RAG Chat, and a read-only Configuration view. See [`docs/architecture.md` §14.3](docs/architecture.md#143-current-state-vs-target) for current state vs. target.

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event transport | Redis Streams | Lightweight, supports consumer groups for worker scaling |
| Cross-module interaction | FastAPI gateway / agent coordinator / shared contracts library only | Enforces loose coupling — see [`docs/architecture.md` §2.2](docs/architecture.md#22-loose-coupling-and-narrow-module-boundaries) |
| Type checking | `pyright --strict` (backend, scoped via `tool.pyright.include`), TypeScript strict (frontend) | Catches errors early; enforces explicit domain types |
| Test coverage | pytest ≥ 85% per backend package (standard; CI gate is aggregate `--cov-fail-under=85`) | Quality gate — missing tests = incomplete work |
| Deployment | Docker containers on Kubernetes or Docker Compose | Hybrid cloud + on-premises support |

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/architecture.md`](docs/architecture.md) | Full high-level architecture and design (source of truth) |
| [`docs/system_architecture_diagram.md`](docs/system_architecture_diagram.md) | Detailed Mermaid system diagram, request flows, and deployment mapping |
| [`docs/onboarding.md`](docs/onboarding.md) | New developer onboarding guide, environment setup, conventions, and how-to examples |
| [`docs/backlog/README.md`](docs/backlog/README.md) | Live, dependency-ordered platform backlog (planned/in-progress/done across all modules and cross-cutting concerns). Per-module files under `docs/backlog/`. |
| [`backend/README.md`](backend/README.md) | Backend setup, module overview, development commands |
| [`chili_app/README.md`](chili_app/README.md) | Frontend setup, page structure, development commands |
