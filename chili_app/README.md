# chili_app — chiliAI Frontend

React 19 + TypeScript + Vite 8 single-page application for the chiliAI analyst workbench.

> Full architecture: [`docs/architecture.md`](../docs/architecture.md). Frontend details: [`docs/architecture.md` §8](../docs/architecture.md#8-frontend-architecture).

## Current State

Routed React 19 + TypeScript workbench prototype. `src/App.tsx` mounts
`<AppProviders>` (QueryClient + SessionProvider) and a `RouterProvider`
defined in `src/app/router.tsx`. The Phase 5 page tree under
`src/pages/*Page.tsx` is the live one. Knowledge Base Manager uses the live
backend KB repository, and Investigation Workbench uses KB-scoped live graph
search/detail/neighborhood endpoints. Alerts, cases, evidence packs, policy
items, workflows, and RAG conversations are backed by the current backend
repository/service paths. Remaining live-data gaps are concentrated in
entity-scoped analytics shortcuts and production hardening of projections.

The Knowledge Base Manager supports document upload and config-defined
structured record feeds. File-upload record feeds parse selected `.csv` and
`.jsonl` files automatically for client-side preview and validation messaging;
the backend records API remains the canonical parser/validator on submission.
Document and records-file uploads go through `apiUploadWithProgress`
(`XMLHttpRequest`, since `fetch` cannot observe request-body upload progress),
rendering an accessible progress bar during upload and a Retry button on
failure. Submission receipts surface in the run timeline with an
"X accepted, Y duplicate, Z rejected" summary, a duplicate-submission (no-op)
indicator, and a bounded list of rejected-row reasons.

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
| **Investigation Workbench** | Core analyst view — active KB selection, live entity search/detail/neighborhood, capability-gated dossier tabs (Signals, Network, Policy, Evidence) |
| **Case Management** | Queue, inspect, and update investigation cases; promote alerts to cases |
| **Policy Intelligence** | Review policy items and triage accepted/rejected/deferred/escalated outcomes |
| **RAG Chat** | Conversational interface for querying knowledge bases through the backend RAG service and durable conversation routes |
| **Configuration** | Config Manager — active-config summary, domain pack switcher, and active-pack YAML editor with dry-run validation and hot-swap apply (see "Config Manager" below) |

## Implemented Routes

Routes are defined in `src/app/router.tsx`. `AppProviders` wraps the app with
`QueryClientProvider` + `SessionProvider`, and the `/` route tree is wrapped in
`<AuthGuard><AppShell /></AuthGuard>`; unauthenticated requests redirect to
`/login`. A catch-all under `/` renders `<PagePlaceholder>` for any
domain-configured page id that doesn't yet have a built component.

| Route | View |
|------|------|
| `/login` | Sign-in landing page (no auth required) |
| `/dashboard` | Dashboard with KPI cards and recent activity |
| `/alerts` | Alert feed with filters, bulk actions, and realtime status |
| `/investigation`, `/investigation/:entityId` | Graph workbench |
| `/cases` | Case management queue |
| `/knowledge-bases` | Ingestion Studio — knowledge base list (scoped to the active domain by default, with a show-all-domains toggle), detail, document inventory |
| `/policy` | Policy intelligence item queue |
| `/housing` | Air Force housing executive dashboard — filter-driven summary band above an Albers CONUS installation health map, status/branch/command filter strip, ranking, status context (see "Housing dashboard" below) |
| `/scorecards/:runId?kb=<kbId>` | Scorecard run viewer — graded sections, metric health/completeness chips, citations, JSON/Markdown export (see "Housing dashboard" below) |
| `/rag-chat` | RAG chat shell backed by the selected knowledge base |
| `/configuration` | Config Manager (pack switcher + active-pack YAML editor with validate/apply) |

## Known Prototype Gaps

- The Config Manager has no raw pack read/write endpoint yet: "Validate" dry-runs the edited YAML buffer, but "Apply" re-validates and hot-swaps the **on-disk** pack file — edits made in the editor are never persisted (charted as future config-write work in `docs/backlog/config.md` config.07/config.14 and `frontend.25/26`).
- The KB domain-mismatch badge (`KbDomainBadge`) renders only on the ingestion KB selector and the KB Manager; other KB pickers (Investigation Workbench, RAG chat) do not badge mismatched KBs yet — follow-up work.
- `src/components/knowledgebase/KbTable.tsx` and `KbDetailView.tsx` are orphaned (not reachable from any routed page); the KB Manager page renders its own table/detail. Fold or remove them when the KB Manager is next reworked.
- Some non-Investigation graph/entity discovery flows are still incomplete.
- Entity-scoped analytics shortcuts still use the remaining `ApiState` analytics composition until they migrate to the same persistence-backed query path as overview/list routes.
- RAG chat uses the configured backend RAG service in the app factory; direct test construction can still use deterministic in-memory fallbacks.
- There is no standalone `/workflows` page yet; workflow monitoring currently appears in Dashboard counters and the KB Manager run timeline.
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

`package.json` carries an `overrides` entry forcing `js-yaml >= 4.3.0`
(GHSA-52cp-r559-cp3m / GHSA-h67p-54hq-rp68, quadratic-CPU DoS): the fix is
in-range for every consumer except `@redocly/openapi-core` (a transitive
dev dependency of `openapi-typescript`), which pins the vulnerable `4.2.0`
exactly and has no fixed release yet. Drop the override once a redocly
release depends on `js-yaml >= 4.3.0`. CI's `npm audit --audit-level=high`
gate enforces this.

`npm run codegen:api` reads `chili_app/openapi.json`; it does not call a live backend. When backend HTTP contracts change, regenerate the snapshot from the repo root first:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
```

## E2E Tests

End-to-end tests use [Playwright](https://playwright.dev/) and live in `e2e/`.
They run against the **full running stack** (real API, worker, Neo4j, Qdrant,
Redis, MinIO, Postgres) — there are no `page.route()` mocks. The browser under
test talks to the real backend, so a spec passing means the real
endpoint/component/integration works, not a fixture.

### Running e2e tests

The canonical entrypoint is the repo-root Makefile target, which brings up a
clean stack, seeds it, runs the suite, and tears it down:

```bash
# From repo root
make test-e2e
```

`make test-e2e` does: `docker compose down -v` (clean slate) →
`CHILI_DEV_ANONYMOUS_ROLE=analyst docker compose up -d --build` →
`scripts/wait_for_stack.sh` (polls API `:8000/health` and app `:5173/`) →
`npm run test:e2e` → `docker compose down`.

For iterative local runs against an already-running stack:

```bash
# Bring the stack up once with the analyst override, then:
cd chili_app
npm run test:e2e           # headless Chromium; HTML report in playwright-report/
npm run test:e2e:ui        # interactive Playwright UI
npx playwright test e2e/smoke.spec.ts   # single file
```

### How the suite is seeded

`e2e/global-setup.ts` runs once before any spec: it waits for the API to be
healthy, POSTs `/admin/dev-seed`, and writes the returned ids to
`e2e/.seeded.json` (gitignored). Specs read those ids via `e2e/helpers/seeded.ts`
(`seeded().knowledge_base_id`, etc.) and assert against the real data.

- **`POST /admin/dev-seed`** (`backend/api/routers/dev_seed.py`) is a dev-only
  endpoint, registered only when `CHILI_ENV != production`. It writes a
  deterministic scenario directly to the real stores: a ready KB ("E2E Seed KB"),
  a hub-and-spoke subgraph, an evidence pack, an alert, a policy item, and an
  **independent** open case whose `alert_ids` is empty so the seeded alert stays
  promotable for the promote spec. The scenario is **derived from the active
  `DomainConfig`** (no hardcoded domain types): entity/relationship shapes come
  from the pack's declarations, property values are generated from each
  `PropertyDefinition`, and the policy item comes from the pack's own
  `policy_rules`. Under the default medicare pack the seeded display values keep
  the exact strings the suite asserts on ("Redwood DME Group",
  "Redwood DME escalation", confidence 0.96). Two known limits: property
  `pattern` generation supports a pragmatic regex subset (literals, `\d`/`\w`/`\s`,
  character classes, `.`, `{n}`/`{n,m}`/`+`/`*`/`?` — no groups/alternation/negated
  classes; unsupported patterns fall back), and the demo policy item is generated
  only from **entity-target** policy rules (packs with only metric-target rules
  return an empty `policy_item_id`).
- **`CHILI_DEV_ANONYMOUS_ROLE=analyst`** elevates the anonymous user to the
  analyst role (dev-gated in `api/middleware/auth.py`; ignored when
  `CHILI_ENV=production`), so protected pages render without a login flow.
- **Domain guard (automatic)**: global-setup probes `GET /config/domain`
  before seeding and **skips `POST /admin/dev-seed` on any non-medicare
  stack** (logged loudly, naming the active domain). The dev-seed scenario's
  asserted display values belong to the medicare pack, and on another pack
  the seeded KB would become the newest ready/active KB — flipping the
  `/housing` endpoints (and every newest-KB-resolving dashboard) off that
  pack's seeded demo KB (e.g. `make seed-housing`) for the whole run. On a
  housing-pack stack the housing specs therefore run in live mode with no
  env var needed:

  ```bash
  npx playwright test e2e/air-force-housing-scorecards.spec.ts
  ```

- **`E2E_SKIP_DEV_SEED=1`** stays as the **explicit override**: it makes
  global-setup skip `POST /admin/dev-seed` unconditionally (logged loudly),
  including on medicare stacks where the domain guard would otherwise seed.
  Under either skip path, seeded-id specs fail by design.

  The housing specs themselves (`air-force-housing-scorecards.spec.ts`,
  `air-force-housing-context.spec.ts`) are stack-adaptive: they probe
  `GET /housing/installations` and assert live-mode behavior (65 live
  markers, band aggregates recomputed from the API payload,
  viewer/filters/status-context flows) when housing feeds are seeded, or
  reference-mode behavior (public installation layer, placeholder band
  cards, live-only surfaces absent) on the default medicare stack. `ingestion-studio-domain-scoping.spec.ts`
  is domain-adaptive the same way (expectations computed from
  `GET /config/domain` + `GET /knowledgebases`).

### KB teardown (demo-stack safety)

Global setup snapshots the stack's knowledge bases to `e2e/.kb-baseline.json`
**before** seeding, and `e2e/global-teardown.ts` deletes every KB created
after that baseline through the real `DELETE /knowledgebases/{id}` endpoint
(dev-seed KB, spec-created `warn-e2e-*` KBs, domain-mismatch KBs, ...).
Without this, an e2e run leaves a fresh, feed-empty KB that is **newer** than
a seeded demo KB — and because `/housing` and the dashboards resolve the
newest ready/active KB, the leaked KB silently degrades the demo to an empty
view. Teardown fails loudly (non-zero) if any run-created KB could not be
deleted. Pre-existing KBs are never touched.

If a run is interrupted (crash, Ctrl-C) teardown never fires, but the stale
baseline file survives — the next run's global setup detects it and reclaims
the interrupted run's leaked KBs against that stale baseline **before**
taking a fresh snapshot, so leaked KBs can never be adopted as pre-existing.

### Serial execution (shared mutable state)

`playwright.config.ts` sets `fullyParallel: false` and `workers: 1`. The whole
suite shares one real backend seeded with a single scenario, and several specs
mutate that shared state (promote the alert, mark the case in review, submit
feedback). Running serially is intentional — it trades wall-clock for
determinism. Read specs assert on **seed-stable** fields (title, priority),
not on mutable status, so they are order-independent.

| File | Asserts (against real stack) |
|------|------|
| `smoke.spec.ts` | Root renders the app shell (analyst override → no `/login`) |
| `authenticated-shell.spec.ts` | Config-driven sidebar nav ("Alert Feed", "Knowledge Bases") |
| `login-redirect.spec.ts` | Protected route renders without a login redirect (auth disabled) |
| `knowledge-base-list.spec.ts` | Seeded "E2E Seed KB" appears in the Ingestion Studio |
| `ingestion-records.spec.ts` | Records `carrier_claims_a` CSV upload → success receipt + counts in the run timeline |
| `investigation-workbench.spec.ts` | Graph canvas mounts for the seeded entity neighborhood |
| `alert-feed.spec.ts` | Seeded alert rows + severity/status chips + filter bar |
| `alert-acknowledge.spec.ts` | Acknowledge a real alert → status chip transitions |
| `alert-feed-evidence.spec.ts` | "View evidence" renders the real evidence pack reasoning + confidence |
| `case-management.spec.ts` | Seeded case queue + detail (priority chip, "Mark in review") |
| `case-mutation.spec.ts` | "Mark in review" persists via the real API |
| `case-feedback.spec.ts` | Submitting feedback persists and renders in history |
| `case-promote.spec.ts` | Promoting the seeded alert creates a case (real `/cases/promote`) |
| `rag-chat.spec.ts` | New thread → send → real assistant reply renders |
| `policy-intelligence.spec.ts` | Policy gap queue renders from the real API |
| `policy-triage.spec.ts` | Escalating the seeded policy item creates a case via the real triage endpoint |
| `ingestion-document-warnings.spec.ts` | Ragged-CSV upload surfaces worker-persisted parser warnings in the document inventory |
| `air-force-housing-scorecards.spec.ts` | `/housing` dashboard: real CONUS state geography (49 paths), 65 accessible installation markers (public reference layer, or live map points + location-pending accounting when housing feeds are seeded), marker/deep-link selection → detail panel + `?installation=` URL param, summary band rendered above the map with no generation UI (generation is API-only: backend router tests + seed tool), and filter-driven band aggregates pinned against values recomputed from the real API payload (status filter changes them, clear restores) |
| `air-force-housing-context.spec.ts` | Stack-adaptive housing follow-up surfaces: scorecard viewer guard states (missing `?kb=`, unknown run), dashboard run link → viewer with graded sections/health chips + real JSON export download + back-link round trip, "Why this status" drivers pinned to the API's `status_reasons`, filter strip narrowing map markers + ranking rows + status counts together (clear restores), and a zero-failed-runs probe over every housing-domain KB's workflow history |
| `ingestion-studio-domain-scoping.spec.ts` | Domain-adaptive Ingestion Studio scoping: default KB list shows only active-domain (+ legacy unstamped) KBs, show-all-domains toggle reveals the cross-domain list and scopes back down; expected sets computed from the real `/config/domain` + `/knowledgebases` |
| `config-manager.spec.ts` | Pack switcher + YAML editor: dry-run validation errors, apply, and pack hot-swap round-trip (requires an admin session — skips loudly otherwise) |
| `kb-domain-mismatch.spec.ts` | Real pack switch via `/config/switch` → the other-domain KB drops out of the studio's default scoped list, and the show-all-domains toggle reveals it with the warn-only mismatch badge (requires an admin session) |
| `demo-walkthrough.spec.ts` | BL-051 demo-walkthrough mechanical validation, stack-adaptive: reference mode (dev-seed) walks alert row (`triage-numeral` + `.flag-label`) → "View evidence" narrative band → workbench dossier tabs → `/policy`; live mode (a "TN Demo" / `medicare_fraud` / `ready` KB, discovered via `/knowledgebases` or `E2E_DEMO_KB`) additionally asserts a factor-tagged alert, the workbench NETWORK tab's `cluster-membership-panel`, the EVIDENCE tab's `attribution-bars`, and a non-empty `/policy` queue — each live assertion `test.skip()`s with a clear reason when no TN KB exists |

The two config specs are admin-gated: the pack-management routes require the
admin role, so bring the stack up with `CHILI_DEV_ANONYMOUS_ROLE=admin`
(the default `make test-e2e` exports `analyst`; under analyst these specs
skip with a loud message rather than failing). They also drive the UI as the
**supervisor** persona, since both stock packs grant the `configuration` page
to that persona.

### Configuration

- `playwright.config.ts` — testDir, `globalSetup`, `fullyParallel: false`, `workers: 1`, webServer (reuses `:5173`), reporter, retries (0 local / 2 CI)
- `e2e/global-setup.ts` / `e2e/helpers/seeded.ts` — seed the real backend and expose the ids
- `e2e/global-teardown.ts` / `e2e/helpers/kbBaseline.ts` — delete every run-created KB (baseline diff; see "KB teardown" above)
- Artifacts excluded from git: `e2e/.seeded.json`, `e2e/.kb-baseline.json`, `test-results/`, `playwright-report/`, `playwright/.cache/`

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

Knowledge bases carry the `domain_name` that created them; `KbDomainBadge`
(`src/components/knowledgebase/KbDomainBadge.tsx`, predicate in
`domainMismatch.ts`) renders a warning badge when a KB's domain does not match
the active pack. It currently appears on the ingestion KB selector and the KB
Manager (see Known Prototype Gaps for the remaining pickers).

## Config Manager

`/configuration` (`src/pages/ConfigurationPage.tsx`) hosts the Config Manager
(`src/components/config/`): the read-only active-config summary plus two
admin surfaces backed by the admin pack-management API:

- **Pack switcher** (`PackSwitcher.tsx`) — lists the packs discovered by
  `GET /config/packs` (name, domain, validity, active marker) and activates
  one via `POST /config/switch`. A switch is a **no-restart hot-swap**: the
  API validates the candidate (including the production auth guardrail),
  persists the active-pack pointer, atomically rebuilds its dependency
  graph, and publishes `config.updated` so the worker converges too.
- **Active-pack YAML editor** (`ActivePackEditor.tsx`) — seeds a YAML buffer
  from the active config. **Validate is a dry-run**: the edited buffer is
  sent inline to `POST /config/validate` and field-level errors render
  without anything being applied. **Apply re-applies the on-disk pack** via
  `POST /config/apply` — it does *not* persist the edited buffer (there is
  no raw pack read/write endpoint yet; that is charted as future
  config-write work). The intended flow for a content change today is: edit
  the pack file on disk, then Apply to re-validate and hot-swap it.
  `SwapResultBanner.tsx` reports swap success/failure.

Role gating happens at two levels:

- **API**: `GET /config/packs` and `POST /config/validate|apply|switch` are
  `require_role("admin")` — the page mirrors this and hides the admin
  surfaces for non-admin sessions.
- **Navigation**: the `configuration` page id is granted to the
  **supervisor** persona in both stock packs' `ui.roles`, so reaching the
  page in the UI means selecting the supervisor persona while holding an
  admin-capable session.

One switch-semantics consequence worth knowing while developing: once a pack
has been applied/switched, the persisted pointer overrides
`CHILI_CONFIG_PATH` on restart — see the gotcha in
[`../backend/config/README.md`](../backend/config/README.md).

## Housing Dashboard

`/housing` (`src/pages/HousingExecutivePage.tsx`) is the Department of the Air
Force housing demo surface — a map-led executive operating picture over the
real `/housing/installations` endpoint plus the `/scorecards/*` run-viewing
surface. Layout: header → summary band → filter strip → map + detail card →
ranking table. Backend design:
[`docs/architecture.md` §6.8](../docs/architecture.md#68-housing-scorecards--executive-dashboard-branch-af_housing);
statutory metric provenance:
[`docs/research/housing-scorecard-mandates.md`](../docs/research/housing-scorecard-mandates.md).

**Quickstart** (from repo root):

```bash
make dev-domain DOMAIN=department_air_force_housing   # stack with the housing pack
make seed-housing                                     # fresh KB + 6 feed fixture uploads over real HTTP
make seed-housing SEED_ARGS="--scorecards"            # ...plus scorecard runs per template
# open http://localhost:5173/housing
```

Reseeding always targets a **fresh** KB (record ingestion is insert-only; the
seed script refuses a same-named existing KB) — see
`docs/testing/knowledge_base_fixtures/air_force_housing/README.md`. The
housing pack pins the dev-stack services like the other shipped packs, so
seeded demo state (KB, records, scorecard runs) survives API restarts —
reseed only after `make clean` wipes the volumes.

**Map component** (`src/components/housing/InstallationHealthMap.tsx` +
`installationMapGeometry.ts`):

- Real geography: `d3-geo` + `topojson-client` over the pre-projected
  `us-atlas` `states-albers-10m` asset (975×610 Albers USA frame, AK/HI inset
  ids omitted — CONUS + DC, 49 state paths). Fully self-contained: static
  import, no tile servers, no runtime network fetch.
- Markers are real `<button>` elements layered over the SVG: color = status,
  size = open-work-order band, branch (USAF/USSF) as a glyph, `aria-pressed`
  selection state, deterministic west-to-east keyboard order. Co-located
  markers are decluttered with leader legs back to their true anchor.
- Installations without resolvable coordinates (or outside the CONUS frame)
  render in a visible "Location pending" list — never silently dropped.
- With no housing rows ingested, the page falls back to the 65-entry public
  reference layer (`src/data/airForceInstallations.ts`, kept in sync with
  `docs/testing/knowledge_base_fixtures/air_force_housing/installations_reference.csv`
  by a unit test), renders placeholder band cards (no fabricated numbers), and
  the detail card states the statutory-feed requirement honestly.

**Summary band** (`src/components/housing/HousingSummaryBand.tsx`): one
`role=group` band **above the map** carrying every portfolio aggregate — in
live mode nine cards (Reporting, Open WOs, Critical, Occupancy, Condition
index, Satisfaction, Overdue WO rate, UH/MFH supply ratios), all recomputed
client-side from the **filtered** installation set by the pure
`housingFilters.aggregateInstallations()` using the backend read model's
documented weighting semantics (unit-weighted occupancy/condition,
survey-weighted satisfaction, Σ-based rates/ratios; aggregate-input fields on
`HousingInstallationResponse`). With no filters active the band exactly
matches `GET /housing/overview` (unit-test pinned against a fixture mirroring
the backend's router test); subsets with no reporters for a metric show an
honest "n/a". There is no separate readiness/aggregate panel and no
"Generate scorecard" button — scorecard generation is API-only
(`POST /scorecards/runs`, exercised by backend router tests and
`make seed-housing SEED_ARGS="--scorecards"`), retired from the UI 2026-07-07.

**KB selection**: the page's scorecard run links and RAG launches target the
KB chosen by `selectActiveKnowledgeBase()`, which mirrors the backend housing
read model exactly — `ready` KBs preferred, then still-`active` ones
(records-only KBs never transition to `ready`), newest within each band, KBs
pending cleanup excluded — so the KB whose runs the page lists is the KB the
`/housing` endpoints aggregate.

**Filters** (`src/components/housing/HousingFilterStrip.tsx` + the pure
logic module `housingFilters.ts`): status / branch (USAF/USSF) / command
toggle groups — OR within a category, AND across categories, commands derived
from the loaded data. Filters apply simultaneously to the summary band's
aggregates, the map, the ranking table, and the status-strip counts, with an
`aria-live` "Showing X of Y installations" summary and a Clear-filters action. Selection resolves against
the filtered set: a filtered-out selection falls back to the first visible
installation **without** touching the URL, so clearing the filters restores
it. Filter state is component-local by design (not URL-persisted).

**Status context** (live mode): the installation detail card renders a
"Why this status" list straight from the API's `status_reasons` (the same
threshold evaluation that produced the status band — no second threshold
table client-side; honest fallback line when empty) and a rank pill
("#N of M reporting by open work orders") preferring the backend's
`open_work_orders_rank` with a client-side competition-rank fallback whose
denominator counts reporting installations only.

**Scorecard run viewer** (`src/pages/ScorecardRunPage.tsx`, route
`/scorecards/:runId?kb=<kbId>`): renders a persisted run — header with
template, resolved installation name, period, overall-health and run-status
chips (failed runs get a `role=alert` banner, superseded runs an amber one);
graded sections as cards of metric rows with value/unit formatting, health
chips, completeness chips (shown only when not `complete`), citation pills,
warnings, and a computation-description affordance; JSON/Markdown export via
the real export endpoint with client-side blob download. Guard states:
missing `?kb=` context, run-not-found (404), loading, and error. The
dashboard's only entry into the viewer is the detail card's "Scorecards" list
(latest run per template); the viewer's back link returns to
`/housing?installation=<scope_id>`.

## TypeScript Configuration

- Target: ES2023
- Strict checks: `noUnusedLocals`, `noUnusedParameters`, `noFallthroughCasesInSwitch`
- Module resolution: bundler mode
- JSX: react-jsx
