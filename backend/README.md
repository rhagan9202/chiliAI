# chiliAI Backend

Python 3.12 backend for the chiliAI platform — a domain-reconfigurable Graph RAG analytics system.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Backend module details: [`docs/architecture.md` §5](../docs/architecture.md#5-backend-module-decomposition).

## Current State

Early-stage scaffold. `main.py` is a minimal entry point. No service framework, API layer, or test suite is established yet.

## Target Module Structure

```
backend/
├── api/             # FastAPI gateway — routing, validation, DI wiring (no business logic)
├── ingestion/       # Document parsing (PDF, DOCX, HTML, JSON, TXT), chunking, entity extraction
├── graph/           # Abstract graph repository protocol + adapters (Neo4j, Memgraph, Neptune)
├── vectorstore/     # Abstract vector store protocol + adapters (pgvector, Qdrant, Weaviate)
├── embeddings/      # Abstract embedder protocol + adapters (OpenAI, sentence-transformers)
├── rag/             # RAG pipeline — query → embed → search → graph expand → LLM → answer
├── llm/             # Abstract LLM client protocol + adapters (OpenAI, Anthropic, Ollama/vLLM)
├── analytics/
│   ├── timeseries/  # Time-series anomaly detection
│   ├── gnn/         # GNN link prediction, clustering
│   ├── risk/        # Risk scoring engine
│   └── explainability/  # Evidence pack generation, subgraph extraction
├── agent/           # Workflow coordinator — async state machine for multi-step pipelines
├── monitoring/      # Active monitoring — claim stream consumer, alert generation
├── shared/          # Domain types, protocols, utilities (dependency-light, no business logic)
├── config/          # Domain configuration loader (YAML/JSON)
├── events/          # Event bus abstraction + Redis Streams adapter
└── storage/         # Object/file storage abstraction + adapters (S3, MinIO, local FS)
```

## Cross-Module Interaction Rules

Modules interact **only** through:

1. **FastAPI gateway orchestration** — API router → service modules (frontend-initiated)
2. **Agent / workflow coordinator** — event-driven pipelines via Redis Streams
3. **Shared contracts library** (`shared/`) — domain types and protocols

Ad hoc cross-module imports, hidden shared state, and direct implementation coupling are forbidden.

## Development Commands

```bash
# Install (editable, with dev extras when available)
pip install -e ".[dev]"

# API server
uvicorn api.app:create_app --reload --port 8000

# Pipeline worker
python -m agent.coordinator

# Tests
pytest --cov

# Type checking
pyright
```

> These commands target the architecture described in `docs/architecture.md`. Some are not functional until the corresponding modules are implemented.

## Quality Requirements

- **Type checking**: All code must pass `pyright --strict`. Full annotations, no untyped `Any`, explicit domain types.
- **Test coverage**: ≥ 85% for each backend package. Missing tests = incomplete work.
- **Interface-first**: Every external system (graph DB, vector store, LLM, object store) behind an abstract protocol in `<module>/protocols.py` with concrete adapters in `<module>/adapters/`.

## Configuration

The backend reads a domain configuration YAML/JSON file at startup (path set via `CHILI_CONFIG_PATH` environment variable). This configuration defines entity types, relationships, enabled capabilities, and alert thresholds. See [`docs/architecture.md` §9](../docs/architecture.md#9-domain-configuration-model).
