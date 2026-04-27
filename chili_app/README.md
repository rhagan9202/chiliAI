# chili_app — chiliAI Frontend

React 19 + TypeScript + Vite 8 single-page application for the chiliAI analyst workbench.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Frontend details: [`docs/architecture.md` §8](../docs/architecture.md#8-frontend-architecture).

## Current State

Routed React 19 + TypeScript workbench prototype. `src/App.tsx` defines the application routes and wraps the main views in a shared app shell. The UI is functional for local prototype workflows, while some backend capabilities remain stubbed or read-only.

## Target Technology Stack

| Concern | Technology |
|---------|-----------|
| Framework | React 19 (functional components, hooks) |
| Language | TypeScript (strict mode) |
| Build | Vite 8 |
| Routing | React Router v7 |
| Server state | TanStack Query (React Query) |
| Client state | Zustand |
| API client | Generated from FastAPI OpenAPI spec |
| Real-time | WebSocket (alerts, pipeline status) |
| Graph visualization | Cytoscape.js / Sigma.js / React Flow (evaluate) |

## Target Page Structure

| Page | Purpose |
|------|---------|
| **Dashboard** | System overview, recent alerts, knowledge base summaries |
| **Knowledge Base Manager** | List, create, delete KBs; document inventory, add/remove docs |
| **Alert Feed** | Streaming alert list, severity filtering, acknowledgment workflow |
| **Investigation Workbench** | Core analyst view — interactive graph explorer, entity detail, evidence packs, timeline |
| **RAG Chat** | Conversational interface for querying knowledge base via LLM |
| **Configuration** | Domain configuration editor |

## Implemented Routes

| Route | View |
|------|------|
| `/` | Dashboard with KPI cards and recent activity |
| `/knowledgebases` | Knowledge base list and create modal |
| `/knowledgebases/:kbId` | Knowledge base detail, document inventory, upload/delete UI |
| `/alerts` | Alert feed with filters, bulk actions, and realtime status |
| `/investigation` | Graph workbench shell with entity detail, evidence, and timeline panels |
| `/chat` | RAG chat shell backed by the selected knowledge base |
| `/config` | Read-only domain configuration editor |

## Known Prototype Gaps

- Configuration save is disabled until `PUT /config/domain` is implemented.
- Investigation evidence endpoint and some graph/entity discovery flows are still incomplete.
- RAG chat may use stubbed/local responses depending on backend configuration.
- Production bundle size should be revisited with route-level code splitting as the UI grows.

## Development Commands

```bash
npm install       # Install dependencies
npm run dev       # Vite dev server on http://localhost:5173
npm run build     # TypeScript compile + Vite production build
npm run lint      # ESLint check
npm run preview   # Preview production build
```

## Domain-Driven Dynamic UI

The frontend reads domain configuration from `GET /config/domain` at startup. This drives entity labels, icons, relationship labels, enabled analytics panels, and alert thresholds — allowing the same codebase to serve Medicare fraud, food supply chain, or any configured domain without code changes. See [`docs/architecture.md` §9](../docs/architecture.md#9-domain-configuration-model).

## TypeScript Configuration

- Target: ES2023
- Strict checks: `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`
- Module resolution: bundler mode
- JSX: react-jsx
