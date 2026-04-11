# chili_app — chiliAI Frontend

React 19 + TypeScript + Vite 8 single-page application for the chiliAI analyst workbench.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Frontend details: [`docs/architecture.md` §8](../docs/architecture.md#8-frontend-architecture).

## Current State

Vite + React 19 scaffold with template placeholder UI. `src/App.tsx` is still default content.

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
