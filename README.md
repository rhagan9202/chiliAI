# chiliAI

A **domain-reconfigurable Graph RAG analytics platform**. Combines knowledge-graph construction, vector-based retrieval-augmented generation, graph neural networks, time-series analysis, anomaly detection, and explainable AI in a loosely coupled, modular system operated through a browser-based analyst workbench.

> For the full architecture and design, see [`docs/architecture.md`](docs/architecture.md).

---

## Goals

- **Flexible, reconfigurable platform** — built around Graph RAG for analytics/exploration, ML, GNN, explainable AI, time-series analysis, and anomaly detection through loosely coupled, interchangeable capability modules in a Python 3.12 backend.
- **Domain reconfigurability** — a single YAML/JSON configuration surface (or UI wizard) retargets the platform to different domains (entity names, relationships, display labels, enabled capabilities). Examples: Medicare fraud detection, food supply chain monitoring, financial crime.
- **Vendor-agnostic** — graph database (Neo4j, Memgraph, Neptune), vector store (pgvector, Qdrant, Weaviate), LLM provider (OpenAI, Anthropic, Ollama/vLLM), and object storage (S3, MinIO, local FS) are all accessed through abstract interface contracts with concrete adapters.

## Starting Exemplar: Medicare Fraud Detection

### Phase 1 — Build the policy knowledge base (batch)

1. Ingest policy documents (PDF, DOCX, HTML, JSON, TXT)
2. Extract entities, relationships, and metadata → build the policy knowledge graph
3. Embed and index extracted text and graph metrics into a vector store for RAG retrieval

The analyst can view a summary of ingested documents, add or remove documents, delete or create knowledge bases, and rebuild the RAG index.

### Phase 2 — Active monitoring (streaming + batch)

4. Ingest structured and unstructured data — claims records, beneficiary information, provider data, medical records
5. Normalize, chunk, and extract entities → create/update the claims knowledge graph
6. Run analytics pipeline — time-series anomaly detection, GNN link prediction and clustering, risk scoring. Results feed back into the knowledge graph (self-reinforcing loop) and forward to the analyst workbench.
7. Surface alerts with evidence/explainability packs (reasoning, subgraph patterns, confidence scores)
8. Analyst explores and queries the graph for investigation
9. Analyst interacts with the knowledge base via LLM-powered conversational RAG

## Repository Structure

```
chiliAI/
├── backend/        # Python 3.12 backend — FastAPI gateway, workers, analytics modules
├── chili_app/      # React 19 + TypeScript + Vite 8 frontend — analyst workbench SPA
├── docs/           # Architecture, design documents, ADRs
├── infra/          # Deployment configuration (Docker Compose, Kubernetes, IaC)
└── .github/        # CI/CD workflows, Copilot instructions
```

## Quick Start

### Docker (Recommended)

```bash
# Development — full stack with hot-reload
cp .env.example .env          # create local config (gitignored)
make dev                       # or: docker compose -f docker-compose.dev.yaml up --build

# Production — built images, nginx, no hot-reload
make prod                      # or: docker compose up --build -d
```

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

### Backend

```bash
cd backend
# Create and activate a virtual environment, then:
pip install -e ".[dev]"
uvicorn api.app:create_app --reload --port 8000   # API server
python -m agent.coordinator                         # Pipeline worker
pytest --cov                                        # Run tests with coverage
```

> **Current state**: Backend is ~38% implemented — full 16-module structure, protocols, and adapters in place; Neo4j and Qdrant adapters complete; pipeline covers upload→ingest→graph. Frontend is a Vite + React scaffold. See [`docs/project_status_report.md`](docs/project_status_report.md) and [`docs/architecture.md` §14.3](docs/architecture.md#143-current-state-vs-target) for full status.

## Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event transport | Redis Streams | Lightweight, supports consumer groups for worker scaling |
| Cross-module interaction | FastAPI gateway / agent coordinator / shared contracts library only | Enforces loose coupling — see [`docs/architecture.md` §2.2](docs/architecture.md#22-loose-coupling-and-narrow-module-boundaries) |
| Type checking | `pyright --strict` (backend), TypeScript strict (frontend) | Catches errors early; enforces explicit domain types |
| Test coverage | pytest ≥ 85% for backend packages | Quality gate — missing tests = incomplete work |
| Deployment | Docker containers on Kubernetes or Docker Compose | Hybrid cloud + on-premises support |

## Documentation

| Document | Purpose |
|----------|---------|
| [`docs/architecture.md`](docs/architecture.md) | Full high-level architecture and design (source of truth) || [`docs/onboarding.md`](docs/onboarding.md) | **New developer onboarding guide** — environment setup, conventions, how-to examples for adding modules, routes, adapters, and frontend components |
| [`docs/project_status_report.md`](docs/project_status_report.md) | Current implementation status, gap-closure plan, and risk register || [`backend/README.md`](backend/README.md) | Backend setup, module overview, development commands |
| [`chili_app/README.md`](chili_app/README.md) | Frontend setup, page structure, development commands |