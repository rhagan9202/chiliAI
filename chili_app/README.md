# chili_app — chiliAI Frontend

React 19 + TypeScript + Vite 8 single-page application for the chiliAI analyst workbench.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Frontend details: [`docs/architecture.md` §8](../docs/architecture.md#8-frontend-architecture).

## Current State

Routed React 19 + TypeScript workbench prototype. `src/App.tsx` mounts
`<AppProviders>` (QueryClient + SessionProvider) and a `RouterProvider`
defined in `src/app/router.tsx`. The Phase 5 page tree under
`src/pages/*Page.tsx` is the live one. Knowledge Base Manager uses the live
backend KB repository, and Investigation Workbench uses KB-scoped live graph
search/detail/neighborhood endpoints. Some Dashboard, alert, analytics, RAG,
and evidence surfaces still include seeded/demo read models until their live
projections are migrated.

## Target Technology Stack

| Concern | Technology |
|---------|-----------|
| Framework | React 19 (functional components, hooks) |
| Language | TypeScript (strict mode) |
| Build | Vite 8 |
| Routing | React Router v7 |
| Server state | TanStack Query (React Query) |
| Client state | Zustand |
| API client | Typed fetch wrapper (`src/lib/apiClient.ts`) with TanStack Query hooks |
| Real-time | Server-Sent Events for workspace snapshots; WebSocket support remains available |
| Graph visualization | `react-force-graph-2d` |

## Target Page Structure

| Page | Purpose |
|------|---------|
| **Dashboard** | System overview, recent alerts, knowledge base summaries |
| **Knowledge Base Manager** | List, create, delete KBs; document inventory, add/remove docs |
| **Alert Feed** | Streaming alert list, severity filtering, acknowledgment workflow |
| **Investigation Workbench** | Core analyst view — active KB selection, live entity search/detail/neighborhood, evidence packs, timeline |
| **RAG Chat** | Conversational interface for querying knowledge bases; current API path uses seeded/local RAG responses while service-backed vector/LLM wiring is pending |
| **Configuration** | Domain configuration editor |

## Implemented Routes

Routes are defined in `src/app/router.tsx`. The `/` tree is wrapped in
`<AuthGuard>` + `<DomainConfigProvider>`; unauthenticated requests redirect
to `/login`. A catch-all under `/` renders `<PagePlaceholder>` for any
domain-configured page id that doesn't yet have a built component.

| Route | View |
|------|------|
| `/login` | Sign-in landing page (no auth required) |
| `/dashboard` | Dashboard with KPI cards and recent activity |
| `/alerts` | Alert feed with filters, bulk actions, and realtime status |
| `/investigation`, `/investigation/:entityId` | Graph workbench |
| `/cases` | Case management queue |
| `/knowledge-bases` | Knowledge base list, detail, document inventory |
| `/policy` | Policy intelligence gap queue |
| `/rag-chat` | RAG chat shell backed by the selected knowledge base |
| `/configuration` | Read-only domain configuration editor |

## Known Prototype Gaps

- Configuration save is disabled until `PUT /config/domain` is implemented.
- Persisted evidence-pack endpoint and some non-Investigation graph/entity discovery flows are still incomplete.
- Dashboard, alerts, cases, and portions of analytics still rely on seeded/demo read models and should be migrated to live projections in follow-up work.
- RAG chat may use stubbed/local responses depending on backend configuration.
- Production bundle size should be revisited with route-level code splitting as the UI grows.

## Development Commands

```bash
npm install            # Install dependencies
npm run dev            # Vite dev server on http://localhost:5173
npm run build          # TypeScript compile + Vite production build
npm run lint           # ESLint check
npm run test           # Vitest test suite
npm run preview        # Preview production build
npm run codegen:api    # Regenerate API client types from the backend OpenAPI schema
npm run render:architecture  # Render docs/architecture.md diagrams
```

## API Conventions

API DTOs are `snake_case` (matching the Python backend) — there is no
camelCase transformation layer. If you need camelCase, convert at the
page-component boundary; do not introduce a deserialization shim.

The transport (`src/lib/apiClient.ts`, re-exported by `src/api/client.ts`)
sends `credentials: 'include'` on every request and redirects to `/login`
on 401 (except for `/auth/*` paths, which surface the error). The realtime
SSE stream (`src/api/realtime.ts`) opens `EventSource` with
`withCredentials: true` so the server-side `require_role` guard sees the
session cookie.

## Domain-Driven Dynamic UI

The frontend reads domain configuration from `GET /config/domain` at startup. This drives entity labels, icons, relationship labels, enabled analytics panels, and alert thresholds — allowing the same codebase to serve Medicare fraud, food supply chain, or any configured domain without code changes. Investigation display helpers in `src/utils/domainDisplay.ts` derive entity titles, subtitles, chips, and relationship labels from `DomainConfig.ui.display_fields`, `entities`, and `relationships`. See [`docs/architecture.md` §9](../docs/architecture.md#9-domain-configuration-model).

## TypeScript Configuration

- Target: ES2023
- Strict checks: `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`
- Module resolution: bundler mode
- JSX: react-jsx
