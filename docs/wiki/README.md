# chiliAI Developer Wiki

**Verified against codebase:** partially refreshed 2026-06-16; individual pages carry their own verification stamps (they range from 2026-05-20 to 2026-08-28 — check a page's stamp before relying on it).

This wiki is the authoritative **narrative** technical reference for the chiliAI codebase. It documents exact current contracts — signatures, payload shapes, route paths, adapter inventories — so agents and developers can make changes without reading the entire codebase. Where the wiki and the code disagree, the code wins; update the wiki. Where the wiki disagrees with `docs/ledger/` or a module `README.md`, neither automatically wins — compare the dates (each wiki page's stamp, the ledger file's **Reviewed** lines) and verify against the code. It is maintained by the `dev-wiki-curator` agent.

## Relationship to Other Docs

| Doc | Owns |
|-----|------|
| `docs/architecture.md` | *Why* and high-level system shape (C4 diagrams, guiding principles) — the design source of truth |
| `CLAUDE.md` | Operating rules, hard architectural constraints, common commands |
| `backend/README.md`, `chili_app/README.md` | Setup, run commands, current implementation status |
| `docs/ledger/` | **Index** of the public surface (module map, protocol/route/event inventories), originally generated and since re-reviewed in place — `module-map.md` was last reviewed 2026-10-24 and covers every backend package, so it is generally fresher than this wiki |
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

### Modules without a wiki page

The backend has 29 packages (`ls backend/`); these have **no** wiki page. Use [`docs/ledger/module-map.md`](../ledger/module-map.md) and the module README where one exists:

| Module | Reference |
|--------|-----------|
| `cases/` | [`backend/cases/README.md`](../../backend/cases/README.md) |
| `conversations/` | [`backend/conversations/README.md`](../../backend/conversations/README.md) |
| `policy/` | [`backend/policy/README.md`](../../backend/policy/README.md) |
| `scorecards/` | [`backend/scorecards/README.md`](../../backend/scorecards/README.md) |
| `execution/` | [`backend/execution/README.md`](../../backend/execution/README.md) |
| `auditlog/` | [`backend/auditlog/README.md`](../../backend/auditlog/README.md) |
| `capabilities/` | [`backend/capabilities/README.md`](../../backend/capabilities/README.md) |
| `connectors/` | [`backend/connectors/README.md`](../../backend/connectors/README.md) |
| `governance/` | [`backend/governance/README.md`](../../backend/governance/README.md) |
| `playbooks/` | [`backend/playbooks/README.md`](../../backend/playbooks/README.md) |
| `readiness/` | [`backend/readiness/README.md`](../../backend/readiness/README.md) |
| `workflow_definitions/` | [`backend/workflow_definitions/README.md`](../../backend/workflow_definitions/README.md) |

`analytics/features/`, `analytics/identity_resolution/` and `analytics/score_runs/` are not detailed in [modules/analytics.md](modules/analytics.md); see their READMEs ([`backend/analytics/features/README.md`](../../backend/analytics/features/README.md), [`backend/analytics/identity_resolution/README.md`](../../backend/analytics/identity_resolution/README.md), [`backend/analytics/score_runs/README.md`](../../backend/analytics/score_runs/README.md)) and the module map.

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
