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
| **Knowledge Base Manager** | List, create, delete KBs; document inventory, add/remove docs, and show a selected-KB-scoped ingestion workflow timeline |
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

For the live, dependency-ordered list of production-readiness work for the SPA, see [`../docs/backlog/frontend.md`](../docs/backlog/frontend.md) (rolled up in [`../docs/backlog/README.md`](../docs/backlog/README.md)).

## Development Commands

```bash
npm install            # Install dependencies
npm run dev            # Vite dev server on http://localhost:5173
npm run build          # TypeScript compile + Vite production build
npm run lint           # ESLint check
npm run test           # Vitest unit tests (watch mode)
npm run test:run       # Vitest unit tests (single run, for CI)
npm run test:e2e       # Playwright e2e tests (starts Vite automatically if not running)
npm run test:e2e:ui    # Playwright UI mode for interactive test debugging
npm run preview        # Preview production build
npm run codegen:api    # Regenerate API types from checked-in openapi.json
npm run render:architecture  # Render docs/architecture.md diagrams
```

`npm run codegen:api` reads `chili_app/openapi.json`; it does not call a live backend. When backend HTTP contracts change, regenerate the snapshot from the repo root first:

```bash
uv run --project backend python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
```

## E2E Tests

End-to-end tests use [Playwright](https://playwright.dev/) and live in `e2e/`.
The Playwright config (`playwright.config.ts`) targets Chromium and auto-starts
the Vite dev server via `webServer` if nothing is listening on `:5173`.

### Running e2e tests

```bash
# From chili_app/
npm run test:e2e           # headless Chromium run, HTML report written to playwright-report/
npm run test:e2e:ui        # open Playwright UI for interactive debugging
npx playwright test --project=chromium e2e/smoke.spec.ts  # single file
```

### What runs without the backend

All current e2e tests run without the backend. Tests that require authenticated
pages use `page.route()` to intercept and mock API calls at the browser layer,
so no live API server is needed.

| File | Description | Backend needed? |
|------|-------------|-----------------|
| `smoke.spec.ts` | Root → /login redirect; login page renders | No |
| `authenticated-shell.spec.ts` | Mocked auth + domain config → sidebar nav, topbar | No |
| `knowledge-base-list.spec.ts` | Mocked KB list → rows, create form visible | No |
| `login-redirect.spec.ts` | Clicking Sign in navigates to /api/auth/login | No |
| `investigation-workbench.spec.ts` | Mocked KB + search → entity results rendered | No |
| `alert-feed.spec.ts` | Mocked alerts (critical/high/medium) → rows, severity chips, status chips, filter bar visible; severity filter reduces visible rows | No |
| `rag-chat.spec.ts` | Mocked KB list → "no KB" empty state; mocked create conversation + add message → user message + assistant reply + citation chip rendered | No |
| `alert-acknowledge.spec.ts` | Mocked single open alert → click Acknowledge → POST /alerts/:id/acknowledge with empty body asserted via waitForRequest; status chip transitions to "acknowledged"; row button relabelled and disabled | No |
| `case-management.spec.ts` | Mocked 3 cases + case detail → all rows render with status labels; detail panel shows status/priority/assignee chips; clicking a second case row loads its detail with correct chips | No |
| `case-mutation.spec.ts` | Mocked 1 open case → click "Mark in review" → PATCH /cases/:id body asserted `{ status: 'in_review' }` via waitForRequest; detail panel status chip updates to "in_review" after refetch | No |
| `case-feedback.spec.ts` | Mocked 1 open case → fill feedback textarea → POST /cases/:id/feedback body asserted `{ label, evidence_adequacy, missing_evidence, notes }` via waitForRequest; feedback history entry appears after refetch; submit button starts disabled, enabled once textarea is non-empty | No |
| `policy-intelligence.spec.ts` | Mocked 2 policy gaps + detail + cases → gap queue rows render with severity/count chips; detail panel shows first-gap summary; clicking second row switches detail panel title | No |

### Mock patterns and gotcha

All API mocks use **host-anchored patterns** (`http://localhost:5173/api/...`)
rather than `**/api/...` globs. The glob `**/api/auth/me` accidentally matches
Vite module URLs like `/src/api/client.ts` and causes a MIME-type error that
prevents the React app from mounting. The host-anchored form is safe.

Shared mock helpers (auth, domain config, features, SSE stream) live in
`e2e/helpers/mocks.ts`. Call `mockAuthenticatedShell(page)` before navigating
to any protected route.

### Configuration

- `playwright.config.ts` — testDir, webServer, reporter, retries (0 local / 2 CI)
- `e2e/helpers/mocks.ts` — shared `page.route()` helpers with verified shapes
- Artifacts excluded from git: `test-results/`, `playwright-report/`, `playwright/.cache/`

## API Conventions

API DTOs are `snake_case` (matching the Python backend) — there is no
camelCase transformation layer. If you need camelCase, convert at the
page-component boundary; do not introduce a deserialization shim.

Realtime workspace updates use `EventSource` with credentials and compare
successive `RealtimeSnapshotResponse` payloads before invalidating TanStack
Query caches. Keep invalidation targeted: alert count changes refresh alerts,
running workflow count changes refresh workflow queries, and KB status changes
refresh the KB list plus affected KB detail/document queries. Do not re-add
broad analytics or policy invalidation for every heartbeat.

The transport (`src/lib/apiClient.ts`, re-exported by `src/api/client.ts`)
sends `credentials: 'include'` on every request and redirects to `/login`
for non-auth `401` responses. It applies a default 30-second timeout while
preserving caller-provided `AbortSignal`s. UI mutation handlers should use
`apiErrorMessage(error, fallback)` so FastAPI `detail` strings and validation
arrays render as analyst-readable messages.

Page routes are wrapped with `ErrorBoundary` so a rendering failure in one
workbench page does not collapse the authenticated app shell. The Investigation
Workbench keeps selected entity, knowledge base, and graph depth in the URL via
`/investigation/:entityId?kb=<id>&depth=<1-5>` for refresh/share continuity.
The KB Manager run timeline renders `WorkflowRunResponse.last_error` for failed
workflow runs when the backend exposes retry-exhaustion details.

## Domain-Driven Dynamic UI

The frontend reads domain configuration from `GET /config/domain` at startup. This drives entity labels, icons, relationship labels, enabled analytics panels, and alert thresholds — allowing the same codebase to serve Medicare fraud, food supply chain, or any configured domain without code changes. Investigation display helpers in `src/utils/domainDisplay.ts` derive entity titles, subtitles, chips, and relationship labels from `DomainConfig.ui.display_fields`, `entities`, and `relationships`. See [`docs/architecture.md` §9](../docs/architecture.md#9-domain-configuration-model).

## TypeScript Configuration

- Target: ES2023
- Strict checks: `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`
- Module resolution: bundler mode
- JSX: react-jsx
