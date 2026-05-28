# chiliAI Developer Wiki

**Verified against codebase:** 2026-05-20

This wiki is the authoritative technical reference for the chiliAI codebase. It documents exact current contracts — signatures, payload shapes, route paths, adapter inventories — so agents and developers can make changes without reading the entire codebase.

## Relationship to Other Docs

| Doc | Owns |
|-----|------|
| `docs/architecture.md` | *Why* and high-level system shape (C4 diagrams, guiding principles) |
| `CLAUDE.md` | Operating rules, hard architectural constraints, common commands |
| `backend/README.md`, `chili_app/README.md` | Setup, run commands, current implementation status |
| **This wiki** | *What* and exact current detail: signatures, route tables, payload shapes, adapter lists |

## Navigation

### Modules

| File | Purpose |
|------|---------|
| [modules/api.md](modules/api.md) | FastAPI gateway — app factory, middleware, all routers, RBAC |
| [modules/agent.md](modules/agent.md) | Workflow coordinator — pipeline worker, protocols |
| [modules/ingestion.md](modules/ingestion.md) | Document parsing, chunking, entity extraction |
| [modules/graph.md](modules/graph.md) | Graph DB access — protocol, adapters, service |
| [modules/vectorstore.md](modules/vectorstore.md) | Vector store access — protocol, adapters, service |
| [modules/embeddings.md](modules/embeddings.md) | Embedding generation — protocol, adapters, service |
| [modules/rag.md](modules/rag.md) | Retrieval-augmented generation pipeline |
| [modules/llm.md](modules/llm.md) | LLM client abstraction — protocol, adapters |
| [modules/analytics.md](modules/analytics.md) | ML analytics — timeseries, GNN, risk, explainability, metrics |
| [modules/monitoring.md](modules/monitoring.md) | Active monitoring, alert evaluation |
| [modules/records.md](modules/records.md) | Structured/tabular ingestion (CSV/JSONL/api-push) |
| [modules/database.md](modules/database.md) | Postgres + TimescaleDB connection provider |
| [modules/knowledgebases.md](modules/knowledgebases.md) | Knowledge base and document metadata persistence |
| [modules/events.md](modules/events.md) | Redis Streams event bus — protocol, adapters |
| [modules/storage.md](modules/storage.md) | Object storage — protocol, adapters |
| [modules/config.md](modules/config.md) | Domain configuration — DomainConfig schema, loader |
| [modules/shared.md](modules/shared.md) | Shared contracts library — types, protocols, utils |
| [modules/frontend.md](modules/frontend.md) | React SPA — router, pages, API client, stores |

### Contracts

| File | Purpose |
|------|---------|
| [contracts/shared-types.md](contracts/shared-types.md) | Entity, Relationship, Alert, EvidencePack, KnowledgeBase |
| [contracts/api-routes.md](contracts/api-routes.md) | All FastAPI routes: method, path, request, response, RBAC |
| [contracts/events.md](contracts/events.md) | Redis Streams event payload shapes (AnyEvent union) |
| [contracts/domain-config.md](contracts/domain-config.md) | DomainConfig full schema reference |

### Flows

| File | Purpose |
|------|---------|
| [flows/ingestion-flow.md](flows/ingestion-flow.md) | Document upload → parse → chunk → extract → graph → embed → index |
| [flows/records-ingestion-flow.md](flows/records-ingestion-flow.md) | Structured records (CSV/JSONL/push) → raw_records → graph + observations |
| [flows/query-flow.md](flows/query-flow.md) | RAG query: question → embed → vector search → graph expand → LLM |
| [flows/auth-flow.md](flows/auth-flow.md) | Login → OIDC callback → session cookie → RBAC |

### History

| File | Purpose |
|------|---------|
| [CHANGELOG.md](CHANGELOG.md) | Dated log of wiki updates tied to code changes |

## Key Entry Points for Common Tasks

- **Adding a FastAPI route**: read [modules/api.md](modules/api.md), then [contracts/api-routes.md](contracts/api-routes.md)
- **Adding an adapter**: read the relevant module page, check the protocol signature
- **Changing a Pydantic model**: check [contracts/shared-types.md](contracts/shared-types.md) and the module's `service_models.py` entry
- **Adding a Redis event**: read [contracts/events.md](contracts/events.md), verify `events/types.py`
- **Changing domain config**: read [contracts/domain-config.md](contracts/domain-config.md)
- **Understanding a data flow**: see `flows/`
