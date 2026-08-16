# Ingestion Phase 2 — Library / Workspace IA Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the seven jobs crammed into `/knowledge-bases` into a Library (pick a corpus) and a per-KB Workspace with five real routed sections, so the URL — not page-local state — owns which knowledge base and which stage the analyst is looking at.

**Architecture:** `/knowledge-bases` becomes a Library of KB cards. `/knowledge-bases/:kbId` becomes a layout route (header + section tabs + `<Outlet/>`) over Overview / Add data / Data / Runs / Settings. Each section is extracted from `KnowledgeBaseManagerPage` as a standalone feature component *before* the routes are wired, so the old page keeps working (and keeps passing its tests) until a single cutover task deletes it. `useActiveKnowledgeBase` learns to read the KB id from the route path and to express a selection as navigation, restoring UXA-101. The six-step stepper and its `currentStep` state are deleted; stages are routes.

**Tech Stack:** React 19 + TypeScript (Vite 8), react-router 8 (data router), zustand, TanStack Query, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-14-ingestion-experience-redesign-design.md` (§1 routes/IA, §2 add-data entry, §5 state model & decomposition, §6 staged-work protection, §8 phase 2)

**Predecessor:** `docs/superpowers/plans/2026-08-14-ingestion-phase1-truth-and-safety.md` (complete, merged at `ff257c19`). Phase 1's `components/status/` primitives, per-KB draft store, server-hydrated receipts and document-lifecycle inventory are prerequisites and are used throughout.

## Global Constraints

- Frontend: TypeScript strict, no `any`. `cd chili_app && npm run lint` clean, `npm run build` clean, `npm run test:run` green. Fix every warning you surface; do not leave a failure as "pre-existing".
- No backend change is in scope for this phase. If you find yourself editing a Pydantic model, stop — that is phase 3. Consequently **no OpenAPI export / `npm run codegen:api` run is expected**; if `chili_app/openapi.json` changes, you have gone out of scope.
- Frontend wire DTOs import from `chili_app/src/api/contracts.ts` only. Never edit `chili_app/src/lib/api/schema.ts`.
- e2e runs against the full real stack (`make dev` up, then `cd chili_app && npm run test:e2e`). `page.route` patterns must be `/api/`-anchored. A mocked subject is not verification.
- Playwright config is `workers: 1`; KB-creating specs must delete what they create or reuse the shared seeded KB.
- No file above ~300 lines (spec §5). If a section component crosses it, split it.
- Store subscriptions via selectors only — a bare `useIngestionDraftStore()` re-renders on every keystroke in any draft.
- Commit after every task, small commits, conventional-commit subjects.
- Before the final task ends: update `chili_app/README.md`, `docs/architecture.md`, and `.github/copilot-instructions.md` where they describe the `/knowledge-bases` page, its store, or its routes.

## Deferred from the spec (do NOT implement here)

State these in the final task's commit body so the next planner does not go looking for them:

- **Role gating (§1 "Role gating")** — no shipped domain pack declares an `admin` or `viewer` role (`medicare_fraud`, `medicare_fraud_cms_desynpuf`, `food_supply_chain` declare `analyst`/`supervisor`; `department_air_force_housing` declares `executive`/`analyst`), and §10 puts "RBAC enablement in dev packs" out of scope. A client gate written against a role vocabulary no pack declares would either hide ingestion from every user or gate nothing. Phase 2 delivers the *structural* half — destructive actions live alone in Settings — and leaves the gate for whichever phase enables auth in a pack.
- **Confirm stage with replace warnings (§2 Documents)** — depends on the `POST /knowledgebases/{kb}/documents/precheck` endpoint, which is phase 3. Add data keeps phase 1's genuinely-gated single submit.
- **Per-activity readiness chip (§3a)** — phase 3. The workspace header shows counts + the existing `StatusChip`, not an activity summary.
- **Connector source card, multi-feed queue, insert-only banner (§2)** — phase 4.
- **Document inventory pagination (§3b)** — the API supports it; the UI gains it when the Data section needs it. Not a phase-2 bullet in §8.
- **The 207 partial-delete report and "Retry cleanup" (§6)** — `DELETE /knowledgebases/{id}` really does return `207 Multi-Status` with `{knowledge_base_id, pending_cleanup, steps[]}` when a cleanup step fails, and `apiRequest` already returns that body (207 is `response.ok`). It is deferred anyway because the route returns a bare `JSONResponse` with no `response_model`, so the shape is absent from the OpenAPI schema and there is no generated contract type for it. Typing it today would mean hand-writing a wire DTO, which the project forbids. Declaring the response model is a backend change — phase 3. Settings is built here so that phase 3 has one place to add it.
- **`useRealtimeWorkspaceStream` in Overview (§5 liveness)** — `AppShell` already calls it once for the whole app, so the workspace digest is live without a second subscription. Opening another would duplicate the stream, not improve freshness. Nothing to do.
- **Drag-to-stage on document staging (§2)** — never implemented; the orphaned `DropZone` that Task 12 deletes was wired to nothing. Phase 1 salvaged its input-reset and append semantics into `DocumentSourcePanel`; the drop zone itself is still owed to §2 and is not part of the IA split.

## File Structure

```
chili_app/src/utils/knowledgeBaseRoutes.ts              NEW  route vocabulary: paths, parsing, legacy redirect, selection target
chili_app/src/utils/activeKnowledgeBase.ts              MOD  pathId wins over ?kb= / stored / recency
chili_app/src/hooks/useActiveKnowledgeBase.ts           MOD  reads the route path; selection navigates
chili_app/src/stores/ingestionDraftStore.ts             NEW  replaces ingestionStudioStore; no currentStep, no mixed issue bucket
chili_app/src/stores/ingestionStudioStore.ts            DEL
chili_app/src/components/ingestion/IngestionStepper.tsx DEL
chili_app/src/lib/ingestion/types.ts                    MOD  drop IngestionStepId
chili_app/src/lib/ingestion/validateIngestion.ts        MOD  rename validateRequiredWizardState → validateIngestionPrerequisites

chili_app/src/features/kb/data/DocumentInventory.tsx    NEW  extracted from the manager page
chili_app/src/features/kb/data/DocumentPreview.tsx      NEW  extracted from the manager page
chili_app/src/features/kb/data/DataSection.tsx          NEW  route body for /:kbId/data
chili_app/src/features/kb/add-data/AddDataSection.tsx   NEW  source choice + staging + validation + submit
chili_app/src/features/kb/runs/RunsSection.tsx          NEW  run timeline + score-run panel
chili_app/src/features/kb/settings/SettingsSection.tsx  NEW  identity details + delete-with-typed-name
chili_app/src/features/kb/overview/OverviewSection.tsx  NEW  situation sentence + handoffs
chili_app/src/features/kb/WorkspaceTabs.tsx             NEW  NavLink section tabs
chili_app/src/features/kb/library/KnowledgeBaseCardList.tsx NEW  Library cards + domain scoping toggle
chili_app/src/features/kb/library/CreateKnowledgeBasePanel.tsx NEW  focused create form
chili_app/src/features/kb/kb.css                        NEW  library grid, workspace header/tabs
chili_app/src/pages/KnowledgeBaseLibraryPage.tsx        NEW  ~150 lines
chili_app/src/pages/KnowledgeBaseWorkspacePage.tsx      NEW  ~120 lines: header, tabs, outlet
chili_app/src/pages/KnowledgeBaseManagerPage.tsx        DEL  (task 9)
chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx DEL (task 9)
chili_app/src/app/router.tsx                            MOD  nested workspace routes + legacy redirect

chili_app/src/components/knowledgebase/{KbTable,KbTable.module.css,KbDetailView,CreateKbForm,DropZone,DropZone.module.css,DocumentTable,StatusBadge,UploadProgress}  DEL (task 12)

chili_app/src/lib/citationTargets.ts                    MOD  document citations → /:kbId/data?document=
chili_app/src/pages/{PolicyIntelligencePage,InvestigationWorkbenchPage}.tsx MOD  workspace links
chili_app/src/components/knowledgebase/EmptyKnowledgeBaseNotice.tsx MOD  workspace link
chili_app/src/pages/pages.css                           MOD  drop dead ingestion-studio-* rules

chili_app/e2e/{knowledge-base-list,ingestion-studio-domain-scoping,ingestion-records,ingestion-document-warnings,ingestion-truth-safety,kb-domain-mismatch}.spec.ts MOD
chili_app/e2e/kb-workspace-navigation.spec.ts           NEW  routes, redirects, URL-owned selection
```

---

### Task 1: Route vocabulary — one module that knows what a knowledge-base URL means

Every later task asks the same three questions (what path does this KB+section have? what KB is this path about? where does a KB selection go from here?). Answer them once, in a pure module with no React and no router import, so the answers are cheap to test and impossible to disagree with.

**Files:**
- Create: `chili_app/src/utils/knowledgeBaseRoutes.ts`
- Test: `chili_app/src/utils/__tests__/knowledgeBaseRoutes.test.ts`

**Interfaces:**
- Produces:
  - `KNOWLEDGE_BASES_ROUTE: '/knowledge-bases'`
  - `WORKSPACE_SECTIONS: readonly ['overview','add','data','runs','settings']`
  - `type WorkspaceSection = 'overview'|'add'|'data'|'runs'|'settings'`
  - `isWorkspaceSection(value: string | undefined): value is WorkspaceSection`
  - `knowledgeBaseWorkspacePath(knowledgeBaseId: string, section?: WorkspaceSection): string`
  - `type WorkspaceMatch = { knowledgeBaseId: string; section: WorkspaceSection }`
  - `matchWorkspacePath(pathname: string): WorkspaceMatch | null`
  - `legacyWorkspaceRedirect(search: URLSearchParams): string | null`
  - `knowledgeBaseSelectionTarget(pathname: string, knowledgeBaseId: string): string | null`

- [ ] **Step 1: Write the failing test**

```ts
// chili_app/src/utils/__tests__/knowledgeBaseRoutes.test.ts
import { describe, expect, it } from 'vitest'

import {
  knowledgeBaseSelectionTarget,
  knowledgeBaseWorkspacePath,
  legacyWorkspaceRedirect,
  matchWorkspacePath,
} from '../knowledgeBaseRoutes'

describe('knowledgeBaseWorkspacePath', () => {
  it('defaults to the overview section, which has no path segment', () => {
    expect(knowledgeBaseWorkspacePath('kb-1')).toBe('/knowledge-bases/kb-1')
  })

  it('appends the section for every other section', () => {
    expect(knowledgeBaseWorkspacePath('kb-1', 'data')).toBe('/knowledge-bases/kb-1/data')
    expect(knowledgeBaseWorkspacePath('kb-1', 'runs')).toBe('/knowledge-bases/kb-1/runs')
  })

  it('encodes ids that are not URL-safe', () => {
    expect(knowledgeBaseWorkspacePath('a b/c', 'add')).toBe('/knowledge-bases/a%20b%2Fc/add')
  })
})

describe('matchWorkspacePath', () => {
  it('reads the id and defaults to overview', () => {
    expect(matchWorkspacePath('/knowledge-bases/kb-1')).toEqual({
      knowledgeBaseId: 'kb-1',
      section: 'overview',
    })
  })

  it('reads the section when present, and decodes the id', () => {
    expect(matchWorkspacePath('/knowledge-bases/a%20b/settings')).toEqual({
      knowledgeBaseId: 'a b',
      section: 'settings',
    })
  })

  it('tolerates a trailing slash', () => {
    expect(matchWorkspacePath('/knowledge-bases/kb-1/')).toEqual({
      knowledgeBaseId: 'kb-1',
      section: 'overview',
    })
  })

  it('does not match the library itself', () => {
    expect(matchWorkspacePath('/knowledge-bases')).toBeNull()
    expect(matchWorkspacePath('/knowledge-bases/')).toBeNull()
  })

  it('does not match an unknown section or a deeper path', () => {
    expect(matchWorkspacePath('/knowledge-bases/kb-1/bogus')).toBeNull()
    expect(matchWorkspacePath('/knowledge-bases/kb-1/data/extra')).toBeNull()
  })

  it('does not match another page', () => {
    expect(matchWorkspacePath('/alerts')).toBeNull()
    expect(matchWorkspacePath('/knowledge-basesX/kb-1')).toBeNull()
  })
})

describe('legacyWorkspaceRedirect', () => {
  it('sends ?kb= to that knowledge base overview', () => {
    expect(legacyWorkspaceRedirect(new URLSearchParams('kb=kb-1'))).toBe(
      '/knowledge-bases/kb-1',
    )
  })

  it('sends ?kb=&document= to the data section, carrying the chunk', () => {
    expect(
      legacyWorkspaceRedirect(new URLSearchParams('kb=kb-1&document=doc-9&chunk=3')),
    ).toBe('/knowledge-bases/kb-1/data?document=doc-9&chunk=3')
  })

  it('drops a document without a knowledge base — it addresses nothing', () => {
    expect(legacyWorkspaceRedirect(new URLSearchParams('document=doc-9'))).toBeNull()
  })

  it('returns null when there is nothing legacy to redirect', () => {
    expect(legacyWorkspaceRedirect(new URLSearchParams())).toBeNull()
  })
})

describe('knowledgeBaseSelectionTarget', () => {
  it('keeps the current section when switching knowledge base inside a workspace', () => {
    expect(knowledgeBaseSelectionTarget('/knowledge-bases/kb-1/runs', 'kb-2')).toBe(
      '/knowledge-bases/kb-2/runs',
    )
  })

  it('opens a workspace when selecting from the library', () => {
    expect(knowledgeBaseSelectionTarget('/knowledge-bases', 'kb-2')).toBe(
      '/knowledge-bases/kb-2',
    )
  })

  it('returns null elsewhere, where the selection belongs in ?kb=', () => {
    expect(knowledgeBaseSelectionTarget('/alerts', 'kb-2')).toBeNull()
    expect(knowledgeBaseSelectionTarget('/investigation/e-1', 'kb-2')).toBeNull()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd chili_app && npm run test:run -- src/utils/__tests__/knowledgeBaseRoutes.test.ts`
Expected: FAIL — `Failed to resolve import "../knowledgeBaseRoutes"`.

- [ ] **Step 3: Write the implementation**

```ts
// chili_app/src/utils/knowledgeBaseRoutes.ts

/**
 * What a knowledge-base URL means.
 *
 * The URL is the single source of truth for which knowledge base and which
 * stage the analyst is looking at (spec §5). That only holds if every caller
 * agrees on the grammar, so the grammar lives here — deliberately free of
 * React and of react-router, so it is cheap to test and cannot drift with a
 * router upgrade.
 */

export const KNOWLEDGE_BASES_ROUTE = '/knowledge-bases'

export const WORKSPACE_SECTIONS = ['overview', 'add', 'data', 'runs', 'settings'] as const

export type WorkspaceSection = (typeof WORKSPACE_SECTIONS)[number]

const SECTION_SET: ReadonlySet<string> = new Set<string>(WORKSPACE_SECTIONS)

export function isWorkspaceSection(value: string | undefined): value is WorkspaceSection {
  return value !== undefined && SECTION_SET.has(value)
}

/** Overview is the workspace root: it has no section segment of its own. */
export function knowledgeBaseWorkspacePath(
  knowledgeBaseId: string,
  section: WorkspaceSection = 'overview',
): string {
  const base = `${KNOWLEDGE_BASES_ROUTE}/${encodeURIComponent(knowledgeBaseId)}`
  return section === 'overview' ? base : `${base}/${section}`
}

export type WorkspaceMatch = {
  knowledgeBaseId: string
  section: WorkspaceSection
}

function withoutTrailingSlash(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
}

/**
 * The knowledge base and section a path addresses, or null when the path is
 * not a workspace. An unknown section is *not* a workspace — it falls through
 * to the router's catch-all rather than being silently coerced to overview.
 */
export function matchWorkspacePath(pathname: string): WorkspaceMatch | null {
  const trimmed = withoutTrailingSlash(pathname)
  const prefix = `${KNOWLEDGE_BASES_ROUTE}/`
  if (!trimmed.startsWith(prefix)) {
    return null
  }

  const [rawId, section, ...rest] = trimmed.slice(prefix.length).split('/')
  if (!rawId || rest.length > 0) {
    return null
  }
  if (section !== undefined && !isWorkspaceSection(section)) {
    return null
  }

  return {
    knowledgeBaseId: decodeURIComponent(rawId),
    section: section ?? 'overview',
  }
}

/**
 * Where a pre-split `/knowledge-bases?kb=…` address should land now.
 *
 * Bookmarks, e-mailed links and every citation emitted before this phase use
 * the query-string form; they keep working by redirect rather than by the
 * library growing a second selection mechanism.
 */
export function legacyWorkspaceRedirect(search: URLSearchParams): string | null {
  const knowledgeBaseId = search.get('kb')
  if (!knowledgeBaseId) {
    return null
  }

  const documentId = search.get('document')
  if (!documentId) {
    return knowledgeBaseWorkspacePath(knowledgeBaseId)
  }

  const next = new URLSearchParams()
  next.set('document', documentId)
  const chunk = search.get('chunk')
  if (chunk !== null) {
    next.set('chunk', chunk)
  }
  return `${knowledgeBaseWorkspacePath(knowledgeBaseId, 'data')}?${next.toString()}`
}

/**
 * Where the app-wide knowledge-base picker should navigate when it is used on
 * `pathname`, or null when the selection is better expressed as `?kb=`.
 *
 * Inside the knowledge-bases area the KB *is* the address, so selecting one is
 * navigation (spec §1). Everywhere else the page stays put and only its scope
 * changes.
 */
export function knowledgeBaseSelectionTarget(
  pathname: string,
  knowledgeBaseId: string,
): string | null {
  const match = matchWorkspacePath(pathname)
  if (match) {
    return knowledgeBaseWorkspacePath(knowledgeBaseId, match.section)
  }
  if (withoutTrailingSlash(pathname) === KNOWLEDGE_BASES_ROUTE) {
    return knowledgeBaseWorkspacePath(knowledgeBaseId)
  }
  return null
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd chili_app && npm run test:run -- src/utils/__tests__/knowledgeBaseRoutes.test.ts`
Expected: PASS, 16 cases.

- [ ] **Step 5: Lint and commit**

```bash
cd chili_app && npm run lint
git add chili_app/src/utils/knowledgeBaseRoutes.ts chili_app/src/utils/__tests__/knowledgeBaseRoutes.test.ts
git commit -m "feat(kb): add the knowledge-base route vocabulary"
```

---

### Task 2: The route owns the knowledge-base selection (UXA-101)

Today `useActiveKnowledgeBase` reads `?kb=` and writes `?kb=`. Teach it that a workspace path names a knowledge base, and that selecting one inside the knowledge-bases area is navigation. Nothing renders differently yet — no workspace route exists — but every later task depends on this being true.

**Files:**
- Modify: `chili_app/src/utils/activeKnowledgeBase.ts`
- Modify: `chili_app/src/hooks/useActiveKnowledgeBase.ts`
- Test: `chili_app/src/utils/__tests__/activeKnowledgeBase.test.ts` (add cases)
- Test: `chili_app/src/hooks/__tests__/useActiveKnowledgeBase.test.tsx` (add cases)

**Interfaces:**
- Consumes: `matchWorkspacePath`, `knowledgeBaseSelectionTarget` (Task 1).
- Produces: `ResolveActiveKnowledgeBaseInput` gains `pathId?: string | null`. `useActiveKnowledgeBase()`'s public shape is unchanged; `setActiveKnowledgeBase(id)` now navigates when `knowledgeBaseSelectionTarget` returns a path.

- [ ] **Step 1: Write the failing resolver test**

Append to `chili_app/src/utils/__tests__/activeKnowledgeBase.test.ts` (inside the existing `describe`):

```ts
  it('lets a knowledge base named by the route path win over ?kb= and the stored id', () => {
    expect(
      resolveActiveKnowledgeBaseId({
        knowledgeBases: [medicareKb, housingKb],
        activeDomainName: 'medicare_fraud',
        pathId: housingKb.id,
        requestedId: medicareKb.id,
        storedId: medicareKb.id,
      }),
    ).toBe(housingKb.id)
  })

  it('honours a path id from another domain — the workspace renders what the URL says', () => {
    // Domain scoping is warn-only (spec §1). Silently resolving to a different
    // corpus than the address bar names would make the header disagree with the
    // body it sits above.
    expect(
      resolveActiveKnowledgeBaseId({
        knowledgeBases: [medicareKb, housingKb],
        activeDomainName: 'medicare_fraud',
        pathId: housingKb.id,
        requestedId: null,
        storedId: null,
      }),
    ).toBe(housingKb.id)
  })

  it('falls through when the path names a knowledge base that does not exist', () => {
    expect(
      resolveActiveKnowledgeBaseId({
        knowledgeBases: [medicareKb],
        activeDomainName: 'medicare_fraud',
        pathId: 'kb-deleted',
        requestedId: null,
        storedId: null,
      }),
    ).toBe(medicareKb.id)
  })
```

Read the top of that file first: reuse whatever fixture names it already defines for an in-domain and an out-of-domain knowledge base rather than introducing new ones. If the existing fixtures are inline object literals, hoist two consts named `medicareKb` and `housingKb` and use them in both the existing and the new cases.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/utils/__tests__/activeKnowledgeBase.test.ts`
Expected: FAIL — TypeScript rejects `pathId` (`Object literal may only specify known properties`).

- [ ] **Step 3: Implement the resolver change**

In `chili_app/src/utils/activeKnowledgeBase.ts`, add the field to the input type:

```ts
export interface ResolveActiveKnowledgeBaseInput {
  knowledgeBases: readonly KnowledgeBaseSummaryResponse[]
  activeDomainName: string | null
  requestedId: string | null
  storedId: string | null
  /**
   * A knowledge base named by the route path. On a workspace route the URL is
   * the page, so this outranks everything else and is validated against the
   * full list rather than the in-domain one: domain scoping is warn-only, and
   * a cross-domain workspace must render the corpus its address names.
   */
  pathId?: string | null
}
```

and open `resolveActiveKnowledgeBaseId` with:

```ts
  const pathId = input.pathId ?? null
  if (pathId !== null && input.knowledgeBases.some((item) => item.id === pathId)) {
    return pathId
  }
```

placed immediately before the existing `const inDomain = …` line.

- [ ] **Step 4: Run the resolver test to verify it passes**

Run: `cd chili_app && npm run test:run -- src/utils/__tests__/activeKnowledgeBase.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing hook test**

`chili_app/src/hooks/__tests__/useActiveKnowledgeBase.test.tsx` already has the
helpers these cases need: `kb(id, overrides)` builds a summary,
`setKnowledgeBases([...])` stubs the list query, and `wrapper(initialEntry)`
returns a `MemoryRouter` wrapper. Use them — do not invent parallel helpers.

Two additions are needed first. Extend the wrapper with a location probe so the
navigation cases can observe where the hook sent the router:

```tsx
let observedLocation: Location | null = null

function LocationProbe() {
  observedLocation = useLocation()
  return null
}

function wrapper(initialEntry: string) {
  return ({ children }: { children: ReactNode }) =>
    createElement(
      MemoryRouter,
      { initialEntries: [initialEntry] },
      children,
      createElement(LocationProbe),
    )
}
```

Add `useLocation` and `type Location` to the `react-router` import, `waitFor`
to the `@testing-library/react` import (`act` is already there), and reset
`observedLocation = null` in the existing `beforeEach`.

Then append these four cases inside the existing `describe`:

```tsx
  it('resolves the knowledge base named by a workspace path', () => {
    setKnowledgeBases([kb('kb-1'), kb('kb-2')])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/knowledge-bases/kb-2'),
    })

    expect(result.current.activeKnowledgeBaseId).toBe('kb-2')
  })

  it('keeps a cross-domain workspace knowledge base in the picker list', () => {
    // The route outranks domain scoping, so the picker has to be able to show
    // what is on screen. Without this the top bar's <select> holds a value
    // matching no option, and the browser renders a different KB's name.
    setKnowledgeBases([kb('kb-1'), kb('kb-2', { domain: 'food_supply_chain' })])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/knowledge-bases/kb-2'),
    })

    expect(result.current.activeKnowledgeBaseId).toBe('kb-2')
    expect(result.current.knowledgeBases.map((item) => item.id)).toContain('kb-2')
  })

  it('selecting a knowledge base inside a workspace navigates, keeping the section', async () => {
    setKnowledgeBases([kb('kb-1'), kb('kb-2')])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/knowledge-bases/kb-1/runs'),
    })

    act(() => {
      result.current.setActiveKnowledgeBase('kb-2')
    })

    await waitFor(() => {
      expect(observedLocation?.pathname).toBe('/knowledge-bases/kb-2/runs')
    })
  })

  it('selecting a knowledge base elsewhere still writes ?kb=', async () => {
    setKnowledgeBases([kb('kb-1'), kb('kb-2')])

    const { result } = renderHook(() => useActiveKnowledgeBase(), {
      wrapper: wrapper('/alerts'),
    })

    act(() => {
      result.current.setActiveKnowledgeBase('kb-2')
    })

    await waitFor(() => {
      expect(observedLocation?.pathname).toBe('/alerts')
      expect(observedLocation?.search).toBe('?kb=kb-2')
    })
  })
```

- [ ] **Step 6: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/hooks/__tests__/useActiveKnowledgeBase.test.tsx`
Expected: FAIL — the workspace path resolves to the recency default, and selection writes `?kb=` on `/knowledge-bases/kb-1/runs` instead of navigating.

- [ ] **Step 7: Implement the hook change**

In `chili_app/src/hooks/useActiveKnowledgeBase.ts`:

```ts
import { useCallback, useEffect, useMemo } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'

import {
  knowledgeBaseSelectionTarget,
  matchWorkspacePath,
} from '../utils/knowledgeBaseRoutes'
```

Inside the hook, after `const [searchParams, setSearchParams] = useSearchParams()`:

```ts
  const location = useLocation()
  const navigate = useNavigate()
  // A workspace path names its knowledge base. Reading it here is what makes
  // the top bar, the readiness chip and the page body agree (UXA-101).
  const pathId = matchWorkspacePath(location.pathname)?.knowledgeBaseId ?? null
```

Pass it through to the resolver:

```ts
  const activeKnowledgeBaseId = resolveActiveKnowledgeBaseId({
    knowledgeBases: allKnowledgeBases,
    activeDomainName,
    pathId,
    requestedId,
    storedId,
  })
```

Then make the returned list able to represent it. `knowledgeBases` currently
filters to the active domain and feeds the top bar's picker; a cross-domain
workspace would leave that `<select>` holding a value matching no option, so it
would display some other knowledge base's name over this one's page. Replace
the existing `knowledgeBases` memo with:

```ts
  const inDomainKnowledgeBases = useMemo(
    () =>
      allKnowledgeBases.filter(
        (knowledgeBase) => !isDomainMismatch(knowledgeBase.domain ?? null, activeDomainName),
      ),
    [allKnowledgeBases, activeDomainName],
  )

  // Whatever is active must be selectable, even when domain scoping would hide
  // it: the picker names what is on screen, and a picker that cannot name it
  // shows the wrong knowledge base instead.
  const knowledgeBases = useMemo(() => {
    if (
      activeKnowledgeBaseId === null ||
      inDomainKnowledgeBases.some((item) => item.id === activeKnowledgeBaseId)
    ) {
      return inDomainKnowledgeBases
    }
    const active = allKnowledgeBases.find((item) => item.id === activeKnowledgeBaseId)
    return active ? [...inDomainKnowledgeBases, active] : inDomainKnowledgeBases
  }, [allKnowledgeBases, inDomainKnowledgeBases, activeKnowledgeBaseId])
```

Note the ordering constraint: `activeKnowledgeBaseId` must be computed before
this memo, so move the `resolveActiveKnowledgeBaseId` call above it.

and replace `setActiveKnowledgeBase`:

```ts
  const setActiveKnowledgeBase = useCallback(
    (id: string) => {
      rememberKnowledgeBase(id)
      // Inside the knowledge-bases area the knowledge base is the address, so
      // choosing one is navigation and the current section is preserved.
      const target = knowledgeBaseSelectionTarget(location.pathname, id)
      if (target !== null) {
        navigate(target, { replace: true })
        return
      }
      // Elsewhere the page stays put; only its scope changes. Replace rather
      // than push so switching does not stack history entries.
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current)
          next.set(KNOWLEDGE_BASE_SEARCH_PARAM, id)
          return next
        },
        { replace: true },
      )
    },
    [location.pathname, navigate, rememberKnowledgeBase, setSearchParams],
  )
```

- [ ] **Step 8: Run the full frontend suite**

Run: `cd chili_app && npm run test:run && npm run lint && npm run build`
Expected: all green. `AppShell.test.tsx` mocks this hook, so it is unaffected.

- [ ] **Step 9: Commit**

```bash
git add chili_app/src/utils/activeKnowledgeBase.ts chili_app/src/hooks/useActiveKnowledgeBase.ts chili_app/src/utils/__tests__/activeKnowledgeBase.test.ts chili_app/src/hooks/__tests__/useActiveKnowledgeBase.test.tsx
git commit -m "feat(kb): let the route path own the active knowledge base"
```

---

### Task 3: Delete the stepper and the state that fed it

The six-step stepper gates nothing, is not clickable, can never reach its `submit` step, and is mutated from ten call sites. Stages become routes in this phase, so the stepper and `currentStep` go now — before any section is extracted, so no extracted component is written against them. The draft store loses its mixed `validationIssues` bucket at the same time: parse results stay (they are the outcome of an action), backend errors move onto the mutations that produced them.

**Files:**
- Create: `chili_app/src/stores/ingestionDraftStore.ts`
- Delete: `chili_app/src/stores/ingestionStudioStore.ts`
- Delete: `chili_app/src/components/ingestion/IngestionStepper.tsx`
- Delete: `chili_app/src/components/ingestion/__tests__/IngestionStepper.test.tsx`
- Rename: `chili_app/src/stores/__tests__/ingestionStudioStore.test.ts` → `chili_app/src/stores/__tests__/ingestionDraftStore.test.ts`
- Modify: `chili_app/src/lib/ingestion/types.ts`
- Modify: `chili_app/src/lib/ingestion/validateIngestion.ts`
- Modify: `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`
- Modify: `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`
- Modify: `chili_app/src/components/ingestion/ingestion.css` (drop `.ingestion-stepper*` rules)

**Interfaces:**
- Produces: `useIngestionDraftStore`, `useIngestionDraft(kbId: string | null): IngestionDraft`, `hasStagedWork(draft: IngestionDraft): boolean`, `emptyDraft(): IngestionDraft`, and `type IngestionDraft = { sourceType: IngestionSourceType | null; selectedFeedName: string | null; pendingFiles: File[]; pendingRecordFile: File | null; parsedRows: Record<string, unknown>[]; parseIssues: ValidationIssue[] }`. Store actions: `updateDraft(kbId: string, patch: Partial<IngestionDraft>): void`, `clearDraft(kbId: string): void`, `reset(): void`.
- Produces: `validateIngestionPrerequisites` replaces `validateRequiredWizardState` (same signature).
- Removed: `IngestionStepId`, `useIngestionStudioStore`, `setCurrentStep`, `addValidationIssues`, `IngestionDraft.validationIssues`.

- [ ] **Step 1: Write the failing store test**

```ts
// chili_app/src/stores/__tests__/ingestionDraftStore.test.ts
import { beforeEach, describe, expect, it } from 'vitest'

import {
  emptyDraft,
  hasStagedWork,
  useIngestionDraftStore,
} from '../ingestionDraftStore'

function file(name: string): File {
  return new File(['x'], name, { type: 'text/plain' })
}

describe('ingestionDraftStore', () => {
  beforeEach(() => {
    useIngestionDraftStore.getState().reset()
  })

  it('keeps each knowledge base’s staging to itself', () => {
    const { updateDraft } = useIngestionDraftStore.getState()
    updateDraft('kb-1', { pendingFiles: [file('a.txt')] })
    updateDraft('kb-2', { pendingFiles: [file('b.txt')] })

    const drafts = useIngestionDraftStore.getState().draftsByKb
    expect(drafts['kb-1'].pendingFiles.map((item) => item.name)).toEqual(['a.txt'])
    expect(drafts['kb-2'].pendingFiles.map((item) => item.name)).toEqual(['b.txt'])
  })

  it('clearing one draft leaves the others intact', () => {
    const { updateDraft, clearDraft } = useIngestionDraftStore.getState()
    updateDraft('kb-1', { pendingFiles: [file('a.txt')] })
    updateDraft('kb-2', { pendingFiles: [file('b.txt')] })

    clearDraft('kb-1')

    const drafts = useIngestionDraftStore.getState().draftsByKb
    expect(drafts['kb-1']).toBeUndefined()
    expect(drafts['kb-2'].pendingFiles).toHaveLength(1)
  })

  it('has no step state — stages are routes now', () => {
    expect('currentStep' in useIngestionDraftStore.getState()).toBe(false)
  })

  it('reports staged work for files, a records file, or parsed rows', () => {
    expect(hasStagedWork(emptyDraft())).toBe(false)
    expect(hasStagedWork({ ...emptyDraft(), pendingFiles: [file('a.txt')] })).toBe(true)
    expect(hasStagedWork({ ...emptyDraft(), pendingRecordFile: file('a.csv') })).toBe(true)
    expect(hasStagedWork({ ...emptyDraft(), parsedRows: [{ id: '1' }] })).toBe(true)
  })

  it('does not count a bare feed choice as staged work', () => {
    // Picking a feed and then leaving loses nothing worth a confirmation.
    expect(hasStagedWork({ ...emptyDraft(), selectedFeedName: 'claims' })).toBe(false)
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/stores/__tests__/ingestionDraftStore.test.ts`
Expected: FAIL — `Failed to resolve import "../ingestionDraftStore"`.

- [ ] **Step 3: Write the new store**

```ts
// chili_app/src/stores/ingestionDraftStore.ts
import { create } from 'zustand'

import type { IngestionSourceType, ValidationIssue } from '../lib/ingestion/types'

/**
 * In-flight staging work for one knowledge base.
 *
 * Three things are deliberately absent. `currentStep` is gone: stages are
 * routes, so the URL says where the analyst is. Backend errors are gone: they
 * belong to the mutation that produced them and clear when it is retried.
 * Derived validation is gone: document and row validation are pure functions of
 * the staged content, recomputed rather than stored. What remains is the work
 * itself — the handles and rows the analyst has assembled but not yet
 * submitted — keyed by the knowledge base it was assembled for, which is what
 * makes a cross-knowledge-base leak unrepresentable.
 */
export type IngestionDraft = {
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  pendingRecordFile: File | null
  parsedRows: Record<string, unknown>[]
  /** Issues produced by the parse itself — an action's result, not a derivation. */
  parseIssues: ValidationIssue[]
}

export const emptyDraft = (): IngestionDraft => ({
  sourceType: null,
  selectedFeedName: null,
  pendingFiles: [],
  pendingRecordFile: null,
  parsedRows: [],
  parseIssues: [],
})

/** Whether leaving would lose something the analyst assembled. */
export function hasStagedWork(draft: IngestionDraft): boolean {
  return (
    draft.pendingFiles.length > 0 ||
    draft.pendingRecordFile !== null ||
    draft.parsedRows.length > 0
  )
}

type IngestionDraftState = {
  draftsByKb: Record<string, IngestionDraft>
  updateDraft: (kbId: string, patch: Partial<IngestionDraft>) => void
  clearDraft: (kbId: string) => void
  reset: () => void
}

export const useIngestionDraftStore = create<IngestionDraftState>((set) => ({
  draftsByKb: {},
  updateDraft: (kbId, patch) =>
    set((state) => ({
      draftsByKb: {
        ...state.draftsByKb,
        [kbId]: { ...(state.draftsByKb[kbId] ?? emptyDraft()), ...patch },
      },
    })),
  clearDraft: (kbId) =>
    set((state) => ({
      draftsByKb: Object.fromEntries(
        Object.entries(state.draftsByKb).filter(([key]) => key !== kbId),
      ),
    })),
  reset: () => set({ draftsByKb: {} }),
}))

// Stable identity so the selector below does not hand back a new object on
// every render (which would re-render its consumer in a loop).
const EMPTY_DRAFT_SINGLETON: IngestionDraft = emptyDraft()

/** The draft for the given knowledge base, or an empty draft when none is selected. */
export function useIngestionDraft(kbId: string | null): IngestionDraft {
  return useIngestionDraftStore((state) =>
    kbId ? state.draftsByKb[kbId] ?? EMPTY_DRAFT_SINGLETON : EMPTY_DRAFT_SINGLETON,
  )
}
```

- [ ] **Step 4: Run the store test to verify it passes**

Run: `cd chili_app && npm run test:run -- src/stores/__tests__/ingestionDraftStore.test.ts`
Expected: PASS, 5 cases.

- [ ] **Step 5: Delete the stepper and its dead types**

```bash
cd /home/rhagan/chiliAI
git rm chili_app/src/components/ingestion/IngestionStepper.tsx \
       chili_app/src/components/ingestion/__tests__/IngestionStepper.test.tsx \
       chili_app/src/stores/ingestionStudioStore.ts \
       chili_app/src/stores/__tests__/ingestionStudioStore.test.ts
```

In `chili_app/src/lib/ingestion/types.ts`, delete the `IngestionStepId` union entirely (it has no other consumer once the stepper is gone).

In `chili_app/src/components/ingestion/ingestion.css`, delete every rule whose selector starts `.ingestion-stepper`.

- [ ] **Step 6: Rename the prerequisite validator**

In `chili_app/src/lib/ingestion/validateIngestion.ts`, rename `validateRequiredWizardState` to `validateIngestionPrerequisites` — there is no wizard any more, and the name would outlive the thing it names. Update the three call sites in `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts` and the import in the manager page.

- [ ] **Step 7: Update the manager page**

In `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`:

1. Replace the store imports with:

```ts
import { useIngestionDraft, useIngestionDraftStore } from '../stores/ingestionDraftStore'
import type { IngestionDraft } from '../stores/ingestionDraftStore'
```

2. Delete the `IngestionStepper` import and its `<Card><IngestionStepper …/></Card>` block, plus the `completedStepIds` / `errorStepIds` consts and the `currentStep` / `setCurrentStep` / `addValidationIssues` selector subscriptions.

3. Delete every `setCurrentStep(...)` call (10 sites) and the `addDraftValidationIssues` helper.

4. Replace the `NextActionsPanel`'s `onWatchRuns` with a no-op removal: drop the `Watch runs` button and the `canWatchRuns` prop. The run timeline is already on screen; a button that re-tinted a stepper tile has nothing left to do.

5. Rename every `patchDraft({ validationIssues: … })` to `patchDraft({ parseIssues: … })`, and read `draft.parseIssues` where `draft.validationIssues` was read.

6. Derive the backend error instead of storing it. Replace the three `onError` blocks' `addDraftValidationIssues([...])` calls with nothing (keep `setUploadError` / `showToast`), and compose the issue list from the mutations:

```ts
  const submitError =
    uploadMutation.error ?? uploadRecordFileMutation.error ?? pushRecordsMutation.error ?? null
  // A backend rejection belongs to the mutation that produced it: it clears
  // when that mutation is retried, without anyone remembering to clear it.
  const backendIssues: ValidationIssue[] = submitError
    ? [
        {
          id: 'ingestion-backend-error',
          source: 'backend',
          severity: 'error',
          message: apiErrorMessage(submitError, 'Submission failed.'),
        },
      ]
    : []
  const currentIssues = [
    ...requiredIssues,
    ...(draft.sourceType === 'documents' ? documentIssues : []),
    ...(draft.sourceType === 'records' ? recordIssues : []),
    ...draft.parseIssues,
    ...backendIssues,
  ]
```

7. Memoize the two derived validators so typing in the records editor stops re-validating the full parsed row set (spec §5):

```ts
  const documentIssues = useMemo(
    () => validateDocumentFiles(draft.pendingFiles, domainConfigQuery.data?.validation),
    [draft.pendingFiles, domainConfigQuery.data?.validation],
  )
  const recordIssues = useMemo(
    () =>
      selectedFeed
        ? validateRecordRows(selectedFeed, draft.parsedRows, {
            recordFile: draft.pendingRecordFile,
          })
        : [],
    [selectedFeed, draft.parsedRows, draft.pendingRecordFile],
  )
```

- [ ] **Step 8: Update the manager page's tests**

In `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`:
- Change the store import to `useIngestionDraftStore` from `../../stores/ingestionDraftStore` and any `reset()` call accordingly.
- Delete the `getStepperItem` helper and every test that asserts on stepper items, step labels, `Step 1`/`Step 2` copy, or `aria-current="step"`.
- Delete any test asserting the `Watch runs` button.
- Keep every other test. They are the behavioural safety net for tasks 4–8.

- [ ] **Step 9: Run the suite**

Run: `cd chili_app && npm run test:run && npm run lint && npm run build`
Expected: all green. Investigate any failure rather than deleting the test — the point of keeping the old page alive is that these tests still mean something.

- [ ] **Step 10: Commit**

```bash
cd /home/rhagan/chiliAI
git add -A chili_app/src
git commit -m "refactor(kb): delete the ingestion stepper and the state that fed it"
```

---

### Task 4: Extract the document inventory and preview

The first section body to come out of the 1131-line page. It moves rather than changes: the manager page imports it back, so the page's existing tests still cover it and any behavioural drift shows up immediately.

**Files:**
- Create: `chili_app/src/features/kb/data/DocumentInventory.tsx`
- Create: `chili_app/src/features/kb/data/DocumentPreview.tsx`
- Create: `chili_app/src/features/kb/data/DataSection.tsx`
- Create: `chili_app/src/features/kb/data/__tests__/DataSection.test.tsx`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks. `DataSection` navigates through the `onStageSource` callback its caller supplies, so it needs neither the route vocabulary nor the draft store. Do not add an import to satisfy this line.
- Produces:
  - `DocumentInventory` — props exactly as the manager page's local `DocumentInventoryProps`, minus `preview`/`previewLoading`/`previewError` (which move to `DocumentPreview`), plus nothing.
  - `DocumentPreview` — `{ documentSelected: boolean; hasDocuments: boolean; preview: KnowledgeBaseDocumentPreviewResponse | null; loading: boolean; error: boolean }`.
  - `DataSection` — `{ knowledgeBaseId: string; onStageSource: () => void }`. Owns the status filter (local state), the focused document (`?document=` search param), the document-delete mutation and its `ConfirmDialog`, and both queries.

- [ ] **Step 1: Move the two components out**

Cut lines 906–1116 of `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (`DOCUMENT_STATUS_FILTERS`, `DocumentInventoryProps`, `DocumentInventory`, and the inline preview `<section>` at its tail).

- `DocumentInventory.tsx` receives `DOCUMENT_STATUS_FILTERS`, `DocumentInventoryProps` (exported as `DocumentInventoryProps`), and `DocumentInventory` — verbatim, minus the trailing preview `<section>` and the three preview props.
- `DocumentPreview.tsx` receives that trailing preview `<section>`, with this signature:

```tsx
import type { KnowledgeBaseDocumentPreviewResponse } from '../../../api/contracts'
import { Chip } from '../../../components/ui/Chip'
import { EmptyState } from '../../../components/ui/EmptyState'
import { ErrorState } from '../../../components/ui/ErrorState'
import { LoadingState } from '../../../components/ui/LoadingState'
import { countLabel } from '../../../utils/countLabel'

type DocumentPreviewProps = {
  documentSelected: boolean
  /** With no documents at all, the inventory has already said so. */
  hasDocuments: boolean
  preview: KnowledgeBaseDocumentPreviewResponse | null
  loading: boolean
  error: boolean
}

export function DocumentPreview({
  documentSelected,
  hasDocuments,
  preview,
  loading,
  error,
}: DocumentPreviewProps) {
  if (!hasDocuments) {
    return null
  }
  // …body moved verbatim from the manager page, reading `documentSelected`
  // where it read `activeDocumentId`, `loading`/`error` where it read
  // `previewLoading`/`previewError`.
}
```

Keep every comment. They record why each empty state is or is not rendered (UXA-305) and are the only place that reasoning exists.

- [ ] **Step 2: Write the section that owns the data**

```tsx
// chili_app/src/features/kb/data/DataSection.tsx
import { useState } from 'react'
import { useSearchParams } from 'react-router'

import {
  useDeleteKnowledgeBaseDocument,
  useKnowledgeBaseDocumentPreview,
  useKnowledgeBaseDocuments,
} from '../../../api/knowledgebases'
import { ConfirmDialog } from '../../../components/status/ConfirmDialog'
import { Card } from '../../../components/ui/Card'
import { ErrorState } from '../../../components/ui/ErrorState'
import { LoadingState } from '../../../components/ui/LoadingState'
import { DocumentInventory } from './DocumentInventory'
import { DocumentPreview } from './DocumentPreview'

type DataSectionProps = {
  knowledgeBaseId: string
  /** Where "Stage a source" should send an analyst with nothing ingested yet. */
  onStageSource: () => void
}

/** Query-string key naming the document under the reader. */
const DOCUMENT_SEARCH_PARAM = 'document'

export function DataSection({ knowledgeBaseId, onStageSource }: DataSectionProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState('all')
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null)

  const documentsQuery = useKnowledgeBaseDocuments(knowledgeBaseId, {
    ...(statusFilter === 'all' ? {} : { status: statusFilter }),
  })
  const deleteDocumentMutation = useDeleteKnowledgeBaseDocument(knowledgeBaseId)
  const documents = documentsQuery.data?.items ?? []

  // The focused document lives in the URL, so a citation can address one and a
  // reload keeps it open. A stale id (filtered out, or deleted) falls back to
  // the first row rather than stranding the reader on nothing.
  const requestedDocumentId = searchParams.get(DOCUMENT_SEARCH_PARAM)
  const activeDocumentId = documents.some((item) => item.id === requestedDocumentId)
    ? requestedDocumentId
    : documents[0]?.id ?? null

  const previewQuery = useKnowledgeBaseDocumentPreview(knowledgeBaseId, activeDocumentId)

  function selectDocument(documentId: string | null) {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (documentId === null) {
          next.delete(DOCUMENT_SEARCH_PARAM)
        } else {
          next.set(DOCUMENT_SEARCH_PARAM, documentId)
        }
        return next
      },
      { replace: true },
    )
  }

  if (documentsQuery.isLoading) {
    return <LoadingState label="Loading documents" />
  }

  if (documentsQuery.isError) {
    return <ErrorState description="This knowledge base's documents could not be loaded. Try again in a moment." />
  }

  return (
    <Card>
      <DocumentInventory
        activeDocumentId={activeDocumentId}
        deleteDisabled={deleteDocumentMutation.isPending}
        documents={documents}
        onDeleteDocument={(documentId) => setConfirmingDeleteId(documentId)}
        onSelectDocument={selectDocument}
        onStageSource={onStageSource}
        onStatusFilterChange={setStatusFilter}
        statusFilter={statusFilter}
      />
      <DocumentPreview
        documentSelected={activeDocumentId !== null}
        error={previewQuery.isError}
        hasDocuments={documents.length > 0}
        loading={previewQuery.isLoading}
        preview={previewQuery.data ?? null}
      />
      <ConfirmDialog
        body={`Removes ${
          documents.find((item) => item.id === confirmingDeleteId)?.filename ?? 'this document'
        } and the graph and vector artifacts built from it.`}
        confirmLabel="Remove document"
        destructive
        onCancel={() => setConfirmingDeleteId(null)}
        onConfirm={() => {
          const documentId = confirmingDeleteId
          setConfirmingDeleteId(null)
          if (!documentId) {
            return
          }
          deleteDocumentMutation.mutate(documentId, {
            onSuccess: () => selectDocument(null),
          })
        }}
        open={confirmingDeleteId !== null}
        title="Remove document"
      />
    </Card>
  )
}
```

- [ ] **Step 3: Write the failing section test**

```tsx
// chili_app/src/features/kb/data/__tests__/DataSection.test.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { DataSection } from '../DataSection'

const documents = [
  {
    id: 'doc-1',
    knowledge_base_id: 'kb-1',
    filename: 'policy.txt',
    content_type: 'text/plain',
    size_bytes: 1024,
    status: 'validated',
    current_status: 'validated',
    created_at: '2026-08-01T00:00:00Z',
    warning_count: 0,
    warning_reasons: [],
  },
  {
    id: 'doc-2',
    knowledge_base_id: 'kb-1',
    filename: 'resume.txt',
    content_type: 'text/plain',
    size_bytes: 512,
    status: 'validated',
    current_status: 'extracted_empty',
    created_at: '2026-08-02T00:00:00Z',
    warning_count: 0,
    warning_reasons: [],
  },
]

let observedSearch = ''

function SearchProbe() {
  observedSearch = useLocation().search
  return null
}

function renderSection(initialEntry: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route
              path="/knowledge-bases/:kbId/data"
              element={
                <>
                  {children}
                  <SearchProbe />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    )
  }

  return render(<DataSection knowledgeBaseId="kb-1" onStageSource={vi.fn()} />, {
    wrapper: Wrapper,
  })
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()

    if (url.includes('/documents/') && url.includes('/preview')) {
      const documentId = url.split('/documents/')[1].split('/')[0]
      return new Response(
        JSON.stringify({
          knowledge_base_id: 'kb-1',
          document_id: documentId,
          filename: documentId === 'doc-2' ? 'resume.txt' : 'policy.txt',
          preview_text: `preview of ${documentId}`,
          line_count: 1,
          truncated: false,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    }

    if (url.includes('/documents')) {
      const status = new URL(url, 'http://localhost').searchParams.get('status')
      const items = status ? documents.filter((item) => item.current_status === status) : documents
      return new Response(JSON.stringify({ items, total: items.length }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }

    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('DataSection', () => {
  it('opens the document named by ?document=', async () => {
    renderSection('/knowledge-bases/kb-1/data?document=doc-2')

    await waitFor(() => {
      expect(screen.getByText('preview of doc-2')).toBeInTheDocument()
    })
  })

  it('falls back to the first document when ?document= names one that is not listed', async () => {
    renderSection('/knowledge-bases/kb-1/data?document=doc-gone')

    await waitFor(() => {
      expect(screen.getByText('preview of doc-1')).toBeInTheDocument()
    })
  })

  it('writes the selection into the URL so it survives a reload', async () => {
    renderSection('/knowledge-bases/kb-1/data')

    await waitFor(() => expect(screen.getByText('resume.txt')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /resume\.txt/ }))

    await waitFor(() => {
      expect(observedSearch).toBe('?document=doc-2')
    })
  })

  it('filters by the durable lifecycle status', async () => {
    renderSection('/knowledge-bases/kb-1/data')

    await waitFor(() => expect(screen.getByText('policy.txt')).toBeInTheDocument())
    await userEvent.selectOptions(
      screen.getByLabelText('Filter documents by status'),
      'extracted_empty',
    )

    await waitFor(() => {
      expect(screen.queryByText('policy.txt')).not.toBeInTheDocument()
      expect(screen.getByText('resume.txt')).toBeInTheDocument()
    })
  })

  it('confirms before removing a document', async () => {
    renderSection('/knowledge-bases/kb-1/data?document=doc-1')

    await waitFor(() => expect(screen.getByText('policy.txt')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Remove document' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('policy.txt')
  })
})
```

- [ ] **Step 4: Run it to verify it fails, then passes**

Run: `cd chili_app && npm run test:run -- src/features/kb/data/__tests__/DataSection.test.tsx`
Expected first: FAIL (module not found). After steps 1–2 are in place: PASS, 5 cases.

- [ ] **Step 5: Point the manager page at the extracted section**

In `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`, replace the final `<Card>` of the aside (the one holding `DocumentInventory` and its `ConfirmDialog`) with:

```tsx
          {activeKnowledgeBaseId ? (
            <DataSection
              knowledgeBaseId={activeKnowledgeBaseId}
              onStageSource={() => {
                const section = sourceStepRef.current
                if (section && typeof section.scrollIntoView === 'function') {
                  section.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }
              }}
            />
          ) : null}
```

and delete the now-unused page-level `documentsQuery`, `documentPreviewQuery`, `deleteDocumentMutation`, `selectedDocumentId`, `activeDocumentId`, `documentStatusFilter`, `confirmingDocumentDeleteId`, and the `documents` const — except where `runTimelineVisible` reads `documents.length`. Replace that with:

```ts
  // The timeline earns its card once there is something to time. Documents are
  // owned by the data section now, so ask the workflow list alone; a knowledge
  // base with documents always has the runs that produced them.
  const runTimelineVisible = workflows.length > 0
```

- [ ] **Step 6: Run the suite and repair the manager page's tests**

Run: `cd chili_app && npm run test:run`
Expected: `KnowledgeBaseManagerPage.test.tsx` cases that asserted on `?document=` deep-linking now exercise the section's URL param instead of page state — update their `initialEntries` from `/knowledge-bases?kb=kb-1&document=doc-x` to include the same params (the manager page still lives at `/knowledge-bases`, and `DataSection` reads `?document=` from wherever it is mounted). Any case that no longer has a home in the page belongs in `DataSection.test.tsx`; move it rather than delete it.

- [ ] **Step 7: Lint, build, commit**

```bash
cd chili_app && npm run lint && npm run build
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "refactor(kb): extract the document inventory into a data section"
```

---

### Task 5: Extract the add-data flow

Everything about staging, validating and submitting moves into one component that owns its own draft, mutations and upload progress. The manager page renders it in place of its two "Step 1 / Step 2" cards.

**Files:**
- Create: `chili_app/src/features/kb/add-data/AddDataSection.tsx`
- Create: `chili_app/src/features/kb/add-data/__tests__/AddDataSection.test.tsx`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`

**Interfaces:**
- Consumes: `useIngestionDraft`, `useIngestionDraftStore` (Task 3); `knowledgeBaseWorkspacePath` (Task 1); the existing `SourceTypeStep`, `DocumentSourcePanel`, `RecordsSourcePanel`, `RecordsPreviewTable`, `ValidationPanel`, `SubmitPanel`, `UploadProgress`.
- Produces: `AddDataSection` — props `{ knowledgeBaseId: string; onSubmitted: () => void }`. `onSubmitted` fires once a submission is accepted; the workspace passes a navigate-to-runs, the manager page passes a no-op.

**Size:** this is the largest thing being moved. If `AddDataSection.tsx` lands above ~300 lines, split it the way the spec's tree does — `add-data/DocumentsFlow.tsx` and `add-data/RecordsFlow.tsx` each owning their own staging, validation and submit, with `AddDataSection` reduced to the source choice and the shared `UploadProgress`. Do that split as part of this task, not later; it is much cheaper before the tests are written against one shape.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/features/kb/add-data/__tests__/AddDataSection.test.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useIngestionDraftStore } from '../../../../stores/ingestionDraftStore'
import { AddDataSection } from '../AddDataSection'

const domainConfig = {
  domain: { name: 'medicare_fraud', display_name: 'Medicare Fraud', description: '' },
  entities: [],
  relationships: [],
  capabilities: {
    timeseries: true,
    gnn: true,
    risk_scoring: true,
    rag_chat: true,
    explainability: true,
    structured_ingestion: true,
  },
  ingestion: {},
  validation: {
    max_file_size_mb: 50,
    allowed_content_types: ['text/plain', 'text/csv', 'application/json'],
    max_query_length: 10000,
    max_rag_question_length: 5000,
  },
  records: { feeds: [] },
  alerts: { thresholds: {} },
}

function renderSection(onSubmitted = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }

  const result = render(
    <AddDataSection knowledgeBaseId="kb-1" onSubmitted={onSubmitted} />,
    { wrapper: Wrapper },
  )
  return { ...result, onSubmitted }
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  useIngestionDraftStore.getState().reset()
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.endsWith('/config/domain')) {
      return new Response(JSON.stringify(domainConfig), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('AddDataSection', () => {
  it('will not submit with nothing staged, and says what is missing', async () => {
    renderSection()

    const submit = await screen.findByRole('button', { name: 'Run ingestion' })
    expect(submit).toBeDisabled()
    expect(screen.getByText('Select source type')).toBeInTheDocument()
  })

  it('stages documents into the draft for this knowledge base only', async () => {
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['{}'], 'claim.json', { type: 'application/json' }),
    )

    await waitFor(() => {
      const drafts = useIngestionDraftStore.getState().draftsByKb
      expect(drafts['kb-1'].pendingFiles.map((file) => file.name)).toEqual(['claim.json'])
      expect(drafts['kb-2']).toBeUndefined()
    })
  })

  it('enables submit once documents are staged and pass client validation', async () => {
    renderSection()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['{}'], 'claim.json', { type: 'application/json' }),
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeEnabled()
    })
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/features/kb/add-data/__tests__/AddDataSection.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the section**

Move, verbatim where possible, out of `KnowledgeBaseManagerPage.tsx`: `runDocumentUpload`, `runRecordFileUpload`, `submitDocuments`, `submitRecords`, `runIngestion`, `beginUpload`, `reportUploadProgress`, `receiptToastMessage`, the `uploadStatus` / `uploadPercent` / `uploadError` / `retryUpload` state, the `canRunIngestion` / `runPending` derivations, the memoized `documentIssues` / `recordIssues` from Task 3, and the two `<Card>` bodies that render `SourceTypeStep` + panels and `ValidationPanel` + `SubmitPanel` + `UploadProgress`.

The component's skeleton:

```tsx
// chili_app/src/features/kb/add-data/AddDataSection.tsx
import { useMemo, useState } from 'react'

import { useDomainConfig } from '../../../api/config'
import { useUploadKnowledgeBaseDocuments } from '../../../api/knowledgebases'
import { usePushRecords, useUploadRecordFile } from '../../../api/records'
import { showToast } from '../../../components/common/toastStore'
import { DocumentSourcePanel } from '../../../components/ingestion/DocumentSourcePanel'
import { RecordsPreviewTable } from '../../../components/ingestion/RecordsPreviewTable'
import { RecordsSourcePanel } from '../../../components/ingestion/RecordsSourcePanel'
import { SourceTypeStep } from '../../../components/ingestion/SourceTypeStep'
import { SubmitPanel } from '../../../components/ingestion/SubmitPanel'
import { UploadProgress } from '../../../components/ingestion/UploadProgress'
import type { UploadStatus } from '../../../components/ingestion/UploadProgress'
import { ValidationPanel } from '../../../components/ingestion/ValidationPanel'
import { Card } from '../../../components/ui/Card'
import { apiErrorMessage } from '../../../lib/apiClient'
import type { ValidationIssue } from '../../../lib/ingestion/types'
import {
  validateDocumentFiles,
  validateIngestionPrerequisites,
  validateRecordFile,
  validateRecordRows,
} from '../../../lib/ingestion/validateIngestion'
import { useIngestionDraft, useIngestionDraftStore } from '../../../stores/ingestionDraftStore'
import type { IngestionDraft } from '../../../stores/ingestionDraftStore'
import type { RecordIngestReceipt } from '../../../api/contracts'

type AddDataSectionProps = {
  knowledgeBaseId: string
  /** Called once the server has accepted a submission. */
  onSubmitted: () => void
}

export function AddDataSection({ knowledgeBaseId, onSubmitted }: AddDataSectionProps) {
  // Selector subscriptions only: a bare store read re-renders this whole flow
  // on every keystroke landing in any knowledge base's draft.
  const updateDraft = useIngestionDraftStore((state) => state.updateDraft)
  const clearDraft = useIngestionDraftStore((state) => state.clearDraft)
  const draft = useIngestionDraft(knowledgeBaseId)
  // …everything else moved from the page, with `activeKnowledgeBaseId`
  // replaced by the non-nullable `knowledgeBaseId` prop and every
  // `if (activeKnowledgeBaseId)` guard around draft writes deleted.
}
```

Two substantive changes while moving:

1. **`patchDraft` loses its guard.** The knowledge base is a required prop now, so `updateDraft(knowledgeBaseId, patch)` is unconditional. Delete `patchDraft`'s `if` and the `addDraftValidationIssues` helper entirely.
2. **Submission success calls `onSubmitted()`.** In all three success handlers, after `clearDraft(knowledgeBaseId)`, call `onSubmitted()` in place of the deleted `setCurrentStep('runs')`.

Wrap the two card bodies in a single fragment; do not re-introduce "Step 1"/"Step 2" headings — replace them with:

```tsx
      <Card>
        <section aria-labelledby="add-data-source" className="ingestion-step-section">
          <div className="ingestion-step-section__header">
            <h2 id="add-data-source">Choose a source</h2>
            <p className="page-copy-block">
              Documents are parsed into chunks and entities. Structured records land in a
              configured feed.
            </p>
          </div>
          {/* SourceTypeStep + the matching panel */}
        </section>
      </Card>

      <Card>
        <section aria-labelledby="add-data-review" className="ingestion-step-section">
          <div className="ingestion-step-section__header">
            <h2 id="add-data-review">Review and submit</h2>
          </div>
          {/* RecordsPreviewTable (records only) + ValidationPanel + SubmitPanel + UploadProgress */}
        </section>
      </Card>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd chili_app && npm run test:run -- src/features/kb/add-data/__tests__/AddDataSection.test.tsx`
Expected: PASS, 3 cases.

- [ ] **Step 5: Point the manager page at it**

Replace the two staging `<Card>`s in `KnowledgeBaseManagerPage.tsx` with:

```tsx
            {activeKnowledgeBaseId ? (
              <AddDataSection knowledgeBaseId={activeKnowledgeBaseId} onSubmitted={() => {}} />
            ) : null}
```

Delete every symbol that moved (state, handlers, imports, `sourceStepRef` if it is now unreferenced — if `DataSection`'s `onStageSource` still uses it, keep the ref and attach it to the wrapper `<div>` around `AddDataSection`).

- [ ] **Step 6: Run the suite and re-home the page's tests**

Run: `cd chili_app && npm run test:run`
The manager page's staging, validation and submission tests still pass, because the same DOM renders through the section. Any that fail do so because they reached into page internals — move those into `AddDataSection.test.tsx`.

- [ ] **Step 7: Lint, build, commit**

```bash
cd chili_app && npm run lint && npm run build
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "refactor(kb): extract the add-data flow into its own section"
```

---

### Task 6: Extract the runs section

The run timeline and score-run panel become one section whose polling only runs while it is mounted (spec §5 liveness) — which is automatic once it stops being rendered on every visit to the page.

**Files:**
- Create: `chili_app/src/features/kb/runs/RunsSection.tsx`
- Create: `chili_app/src/features/kb/runs/__tests__/RunsSection.test.tsx`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`

**Interfaces:**
- Produces: `RunsSection` — props `{ knowledgeBaseId: string; entityCount: number }`. `entityCount` drives the score-run start gate and its adjacent reason text; the workspace already has the KB detail loaded, so the section does not re-fetch it.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/features/kb/runs/__tests__/RunsSection.test.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RunsSection } from '../RunsSection'

function renderSection(entityCount: number) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }

  return render(<RunsSection knowledgeBaseId="kb-1" entityCount={entityCount} />, {
    wrapper: Wrapper,
  })
}

const workflow = {
  id: 'wf-1',
  workflow_type: 'ingestion',
  status: 'completed',
  knowledge_base_id: 'kb-1',
  created_at: '2026-08-15T12:00:00Z',
  updated_at: '2026-08-15T12:01:00Z',
  steps: [],
  metadata: {},
  receipt: null,
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    if (url.includes('/workflows')) {
      return new Response(JSON.stringify({ items: [workflow], total: 1 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    if (url.includes('/score-runs')) {
      return new Response(JSON.stringify({ items: [], total: 0 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }
    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('RunsSection', () => {
  it('renders the runs the server reports', async () => {
    renderSection(12)

    await waitFor(() => {
      expect(screen.getByText('ingestion')).toBeInTheDocument()
    })
  })

  it('disables the score run start and names the blocker when there are no entities', async () => {
    renderSection(0)

    const start = await screen.findByRole('button', { name: 'Start score-all' })
    expect(start).toBeDisabled()
    expect(
      screen.getByText('Start requires ingested entities in this knowledge base.'),
    ).toBeInTheDocument()
  })

  it('enables the score run start once the knowledge base has entities', async () => {
    renderSection(12)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start score-all' })).toBeEnabled()
    })
    expect(
      screen.queryByText('Start requires ingested entities in this knowledge base.'),
    ).not.toBeInTheDocument()
  })
})
```

These labels are verified against the current components, not guessed:
`ScoreRunStatusPanel` renders `Start score-all` (it becomes `Starting` only while
`pendingAction === 'start'`), and `RunTimeline` renders `workflow.workflow_type`
as the run title. The panel's start button renders whether or not a run exists,
so the empty `/score-runs` stub does not hide it.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/features/kb/runs/__tests__/RunsSection.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the section**

Move from the manager page: `workflowsQuery`, `scoreRunsQuery`, `scoreRunQuery`, `selectedScoreRunId`, the three score-run mutations, `scoreRunStartDisabled`, `scoreRunStartReason`, `scoreRunPendingAction`, and the two `<Card>`s holding `RunTimeline` and `ScoreRunStatusPanel`.

```tsx
// chili_app/src/features/kb/runs/RunsSection.tsx
import { useState } from 'react'

import { useWorkflows } from '../../../api/workflows'
import {
  useCancelScoreRun,
  useReplayScoreRun,
  useScoreRun,
  useScoreRuns,
  useStartScoreRun,
} from '../../../api/scoreRuns'
import { RunTimeline } from '../../../components/ingestion/RunTimeline'
import { ScoreRunStatusPanel } from '../../../components/knowledgebase/ScoreRunStatusPanel'
import { Card } from '../../../components/ui/Card'
import { EmptyState } from '../../../components/ui/EmptyState'

type RunsSectionProps = {
  knowledgeBaseId: string
  /** Score runs need something to score; the panel says so when this is 0. */
  entityCount: number
}

export function RunsSection({ knowledgeBaseId, entityCount }: RunsSectionProps) {
  const [selectedScoreRunId, setActiveScoreRunId] = useState<string | null>(null)
  const workflowsQuery = useWorkflows({ knowledgeBaseId })
  const scoreRunsQuery = useScoreRuns(knowledgeBaseId, { limit: 1 })
  const scoreRuns = scoreRunsQuery.data?.items ?? []
  const activeScoreRunId = selectedScoreRunId ?? scoreRuns[0]?.id ?? null
  const scoreRunQuery = useScoreRun(knowledgeBaseId, activeScoreRunId)
  const workflows = workflowsQuery.data?.items ?? []

  const startScoreRunMutation = useStartScoreRun(knowledgeBaseId)
  const cancelScoreRunMutation = useCancelScoreRun(knowledgeBaseId, activeScoreRunId)
  const replayScoreRunMutation = useReplayScoreRun(knowledgeBaseId, activeScoreRunId)

  const scoreRunStartDisabled = entityCount === 0
  // A disabled control explains itself in adjacent text, and the explanation
  // has to match the actual blocker (spec §3c).
  const scoreRunStartReason = scoreRunStartDisabled
    ? 'Start requires ingested entities in this knowledge base.'
    : null
  const scoreRunPendingAction = startScoreRunMutation.isPending
    ? 'start'
    : cancelScoreRunMutation.isPending
      ? 'cancel'
      : replayScoreRunMutation.isPending
        ? 'replay'
        : null

  return (
    <>
      <Card>
        {workflows.length > 0 ? (
          <RunTimeline workflows={workflows} />
        ) : (
          <EmptyState
            description="Submitting documents or records starts a run, and it appears here."
            title="No runs yet"
          />
        )}
      </Card>
      <Card>
        <ScoreRunStatusPanel
          detail={scoreRunQuery.data ?? null}
          disabled={false}
          error={scoreRunQuery.isError ? 'Score run status could not be loaded.' : null}
          loading={scoreRunQuery.isLoading}
          onCancel={() => {
            cancelScoreRunMutation.mutate(undefined, {
              onSuccess: (detail) => setActiveScoreRunId(detail.run.id),
            })
          }}
          onReplay={() => {
            replayScoreRunMutation.mutate(
              { idempotency_key: `score-replay:${activeScoreRunId ?? 'missing'}` },
              { onSuccess: (detail) => setActiveScoreRunId(detail.run.id) },
            )
          }}
          onStart={() => {
            if (scoreRunStartDisabled) {
              return
            }
            const currentRun = scoreRunQuery.data?.run
            startScoreRunMutation.mutate(
              {
                batch_size: 100,
                catalog_version: currentRun?.catalog_version ?? 'cms-fraud-features-v1',
                model_version: currentRun?.model_version ?? 'risk-linear-v1',
              },
              { onSuccess: (detail) => setActiveScoreRunId(detail.run.id) },
            )
          }}
          pendingAction={scoreRunPendingAction}
          startDisabled={scoreRunStartDisabled}
          startReason={scoreRunStartReason}
        />
      </Card>
    </>
  )
}
```

Note: the hardcoded `cms-fraud-features-v1` / `risk-linear-v1` fallbacks stay for now — deleting them requires the pack-config `score_runs` block, which is phase 3 (spec §4.4). Carry them across unchanged rather than inventing a substitute.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd chili_app && npm run test:run -- src/features/kb/runs/__tests__/RunsSection.test.tsx`
Expected: PASS, 3 cases.

- [ ] **Step 5: Point the manager page at it, run the suite, commit**

Replace the timeline + score-run cards with `{activeKnowledgeBaseId ? <RunsSection knowledgeBaseId={activeKnowledgeBaseId} entityCount={knowledgeBase?.entity_count ?? 0} /> : null}` and delete the moved symbols and the now-dead `runTimelineVisible`.

```bash
cd chili_app && npm run test:run && npm run lint && npm run build
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "refactor(kb): extract the runs section"
```

---

### Task 7: Extract the settings section

Deletion moves out of the picker it currently hangs off and into a section of its own, where it is the only thing on screen. The section also becomes the home for the identity details §3c demotes out of the main flow.

**Files:**
- Create: `chili_app/src/features/kb/settings/SettingsSection.tsx`
- Create: `chili_app/src/features/kb/settings/__tests__/SettingsSection.test.tsx`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`

**Interfaces:**
- Consumes: `ConfirmDialog` (phase 1), `formatTimestamp` (phase 1), `useIngestionDraftStore().clearDraft` (Task 3).
- Produces: `SettingsSection` — props `{ knowledgeBase: KnowledgeBaseSummaryResponse; onDeleted: () => void }`. On successful delete it clears that KB's draft (it has nowhere to submit to) and calls `onDeleted`.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/features/kb/settings/__tests__/SettingsSection.test.tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useIngestionDraftStore } from '../../../../stores/ingestionDraftStore'
import { SettingsSection } from '../SettingsSection'

const knowledgeBase = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: 'Active corpus',
  status: 'ready',
  document_count: 8,
  entity_count: 53,
  relationship_count: 21,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
  domain: 'medicare_fraud',
}

function renderSection(onDeleted = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }

  const result = render(
    <SettingsSection knowledgeBase={knowledgeBase} onDeleted={onDeleted} />,
    { wrapper: Wrapper },
  )
  return { ...result, onDeleted }
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  useIngestionDraftStore.getState().reset()
  globalThis.fetch = vi.fn(async () => new Response(null, { status: 204 })) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

describe('SettingsSection', () => {
  it('states the blast radius and refuses to delete until the name is typed', async () => {
    renderSection()

    await userEvent.click(screen.getByRole('button', { name: 'Delete knowledge base' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('8 documents')
    expect(dialog).toHaveTextContent('53 entities')
    expect(dialog).toHaveTextContent('cannot be undone')

    const confirm = within(dialog).getByRole('button', { name: 'Delete knowledge base' })
    expect(confirm).toBeDisabled()

    await userEvent.type(within(dialog).getByRole('textbox'), 'Fraud KB')
    expect(confirm).toBeEnabled()
  })

  it('drops the deleted knowledge base’s draft — it has nowhere to submit to', async () => {
    useIngestionDraftStore.getState().updateDraft('kb-1', {
      pendingFiles: [new File(['x'], 'a.txt', { type: 'text/plain' })],
    })
    const { onDeleted } = renderSection()

    await userEvent.click(screen.getByRole('button', { name: 'Delete knowledge base' }))
    const dialog = await screen.findByRole('dialog')
    await userEvent.type(within(dialog).getByRole('textbox'), 'Fraud KB')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete knowledge base' }))

    await waitFor(() => {
      expect(useIngestionDraftStore.getState().draftsByKb['kb-1']).toBeUndefined()
      expect(onDeleted).toHaveBeenCalled()
    })
  })

  it('shows the identity details as copyable text rather than in the main flow', () => {
    renderSection()

    expect(screen.getByText('kb-1')).toBeInTheDocument()
    expect(screen.getByText('medicare_fraud')).toBeInTheDocument()
  })
})
```

Add `within` to the `@testing-library/react` import.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/features/kb/settings/__tests__/SettingsSection.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the section**

```tsx
// chili_app/src/features/kb/settings/SettingsSection.tsx
import { useState } from 'react'

import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { useDeleteKnowledgeBase } from '../../../api/knowledgebases'
import { ConfirmDialog } from '../../../components/status/ConfirmDialog'
import { formatTimestamp } from '../../../components/status/formatters'
import { Card } from '../../../components/ui/Card'
import { useIngestionDraftStore } from '../../../stores/ingestionDraftStore'
import { countLabel } from '../../../utils/countLabel'

type SettingsSectionProps = {
  knowledgeBase: KnowledgeBaseSummaryResponse
  /** Called after the knowledge base is gone; the workspace it named is too. */
  onDeleted: () => void
}

export function SettingsSection({ knowledgeBase, onDeleted }: SettingsSectionProps) {
  const [confirming, setConfirming] = useState(false)
  const clearDraft = useIngestionDraftStore((state) => state.clearDraft)
  const deleteMutation = useDeleteKnowledgeBase()

  return (
    <>
      <Card>
        <section aria-labelledby="kb-settings-details">
          <h2 id="kb-settings-details">Details</h2>
          {/* Ids and raw timestamps are reference material, not part of the
              working flow — §3c demotes them to a details row like this one. */}
          <dl className="kb-settings__details">
            <dt>Knowledge base id</dt>
            <dd><code>{knowledgeBase.id}</code></dd>
            <dt>Domain</dt>
            <dd>{knowledgeBase.domain ?? 'Not stamped'}</dd>
            <dt>Created</dt>
            <dd>{formatTimestamp(knowledgeBase.created_at)}</dd>
            <dt>Last updated</dt>
            <dd>{formatTimestamp(knowledgeBase.updated_at ?? null)}</dd>
          </dl>
        </section>
      </Card>

      <Card>
        <section aria-labelledby="kb-settings-danger">
          <h2 id="kb-settings-danger">Delete this knowledge base</h2>
          <p className="page-copy-block">
            Deleting removes the corpus and everything derived from it. There is no undo and
            no export.
          </p>
          <button
            className="page-button page-button--secondary"
            disabled={deleteMutation.isPending}
            onClick={() => setConfirming(true)}
            type="button"
          >
            Delete knowledge base
          </button>
        </section>
      </Card>

      <ConfirmDialog
        body={`Deletes ${countLabel(knowledgeBase.document_count, 'document')}, ${countLabel(
          knowledgeBase.entity_count,
          'entity',
          'entities',
        )}, ${countLabel(
          knowledgeBase.relationship_count,
          'relationship',
        )}, and every run recorded against it. This cannot be undone.`}
        confirmLabel="Delete knowledge base"
        confirmTypedText={knowledgeBase.name}
        destructive
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false)
          deleteMutation.mutate(knowledgeBase.id, {
            onSuccess: () => {
              // Its draft has nowhere to submit to now.
              clearDraft(knowledgeBase.id)
              onDeleted()
            },
          })
        }}
        open={confirming}
        title="Delete knowledge base"
      />
    </>
  )
}
```

Add the `.kb-settings__details` rule to `chili_app/src/features/kb/kb.css` (created in Task 9; for now put it at the bottom of `chili_app/src/pages/pages.css` and move it in Task 9):

```css
.kb-settings__details {
  display: grid;
  grid-template-columns: minmax(0, max-content) minmax(0, 1fr);
  gap: 4px 16px;
  margin: 0;
}

.kb-settings__details dt {
  color: var(--c-muted);
  font-size: 12px;
}

.kb-settings__details dd {
  margin: 0;
  overflow-wrap: anywhere;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd chili_app && npm run test:run -- src/features/kb/settings/__tests__/SettingsSection.test.tsx`
Expected: PASS, 3 cases.

- [ ] **Step 5: Point the manager page at it**

In `KnowledgeBaseManagerPage.tsx`, delete the `<ConfirmDialog>` for KB deletion, the `confirmingKnowledgeBaseDelete` state, the `deleteKnowledgeBaseMutation`, and the `deleteDisabled` / `onDelete` props passed to `KnowledgeBaseSelector`. Also delete the `Delete selected knowledge base` button from `KnowledgeBaseSelector.tsx` and its two props. Render the section in the aside:

```tsx
          {knowledgeBase ? (
            <SettingsSection
              knowledgeBase={knowledgeBase}
              onDeleted={() => setSelectedKnowledgeBaseId(null)}
            />
          ) : null}
```

- [ ] **Step 6: Run the suite, repair, commit**

Run: `cd chili_app && npm run test:run && npm run lint && npm run build`
The manager page's delete tests now find the button in the settings card rather than the selector — update their queries, or move them into `SettingsSection.test.tsx` if they were only ever about the dialog.

```bash
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "refactor(kb): give knowledge-base deletion its own settings section"
```

---

### Task 8: Write the overview section

The one section with no predecessor: the next-actions manifest, generalized into a sentence about the knowledge base's situation plus the three handoffs (spec §1). It replaces `NextActionsPanel`.

**Files:**
- Create: `chili_app/src/features/kb/overview/OverviewSection.tsx`
- Create: `chili_app/src/features/kb/overview/__tests__/OverviewSection.test.tsx`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`

**Interfaces:**
- Produces: `OverviewSection` — props `{ knowledgeBase: KnowledgeBaseSummaryResponse; activeDomainName: string | null }`. Self-contained: it derives its own copy and builds its own links from `knowledgeBaseWorkspacePath` and the `?kb=` convention for other pages.
- Produces: `knowledgeBaseSituation(knowledgeBase: KnowledgeBaseSummaryResponse): string` — exported for its own test.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/features/kb/overview/__tests__/OverviewSection.test.tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { knowledgeBaseSituation, OverviewSection } from '../OverviewSection'

const base = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: 'Active corpus',
  status: 'ready',
  document_count: 0,
  entity_count: 0,
  relationship_count: 0,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
  domain: 'medicare_fraud',
}

describe('knowledgeBaseSituation', () => {
  it('says a new knowledge base is empty and what to do about it', () => {
    expect(knowledgeBaseSituation(base)).toBe(
      'This knowledge base is empty. Add documents or structured records to start.',
    )
  })

  it('says ingested-but-not-extracted when documents produced no entities', () => {
    expect(knowledgeBaseSituation({ ...base, document_count: 3 })).toBe(
      '3 documents are ingested but produced no entities yet. Check the runs for extraction problems.',
    )
  })

  it('agrees in number for a single document', () => {
    expect(knowledgeBaseSituation({ ...base, document_count: 1 })).toBe(
      '1 document is ingested but produced no entities yet. Check the runs for extraction problems.',
    )
  })

  it('states what is queryable once entities exist', () => {
    expect(
      knowledgeBaseSituation({
        ...base,
        document_count: 8,
        entity_count: 53,
        relationship_count: 21,
      }),
    ).toBe('53 entities and 21 relationships from 8 documents are ready to investigate.')
  })
})

describe('OverviewSection', () => {
  it('offers the handoffs, disabled with a reason while there is nothing to hand off', () => {
    render(
      <MemoryRouter>
        <OverviewSection activeDomainName="medicare_fraud" knowledgeBase={base} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Investigate entities' })).toBeDisabled()
    expect(
      screen.getByText('Investigating needs at least one extracted entity.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Add data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/add',
    )
  })

  it('enables the handoffs once entities exist and scopes them to this knowledge base', () => {
    render(
      <MemoryRouter>
        <OverviewSection
          activeDomainName="medicare_fraud"
          knowledgeBase={{ ...base, document_count: 8, entity_count: 53 }}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: 'Investigate entities' })).toHaveAttribute(
      'href',
      '/investigation?kb=kb-1',
    )
    expect(screen.getByRole('link', { name: 'Review alerts' })).toHaveAttribute(
      'href',
      '/alerts?kb=kb-1',
    )
    expect(screen.getByRole('link', { name: 'Ask in RAG chat' })).toHaveAttribute(
      'href',
      '/rag-chat?kb=kb-1',
    )
  })

  it('warns when the knowledge base was built under another domain', () => {
    render(
      <MemoryRouter>
        <OverviewSection activeDomainName="food_supply_chain" knowledgeBase={base} />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('kb-domain-mismatch-note')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/features/kb/overview/__tests__/OverviewSection.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the section**

```tsx
// chili_app/src/features/kb/overview/OverviewSection.tsx
import { Link } from 'react-router'

import type { KnowledgeBaseSummaryResponse } from '../../../api/contracts'
import { isDomainMismatch } from '../../../components/knowledgebase/domainMismatch'
import { Card } from '../../../components/ui/Card'
import { countLabel } from '../../../utils/countLabel'
import { knowledgeBaseWorkspacePath } from '../../../utils/knowledgeBaseRoutes'

/**
 * One sentence about where this knowledge base actually stands.
 *
 * Not a status word: the three states a corpus is genuinely in — nothing in
 * it, something in it that produced nothing, something in it that answers
 * questions — need different next actions, and the sentence is what tells them
 * apart before the buttons do.
 */
export function knowledgeBaseSituation(knowledgeBase: KnowledgeBaseSummaryResponse): string {
  if (knowledgeBase.document_count === 0 && knowledgeBase.entity_count === 0) {
    return 'This knowledge base is empty. Add documents or structured records to start.'
  }
  if (knowledgeBase.entity_count === 0) {
    const verb = knowledgeBase.document_count === 1 ? 'is' : 'are'
    return `${countLabel(knowledgeBase.document_count, 'document')} ${verb} ingested but produced no entities yet. Check the runs for extraction problems.`
  }
  return `${countLabel(knowledgeBase.entity_count, 'entity', 'entities')} and ${countLabel(
    knowledgeBase.relationship_count,
    'relationship',
  )} from ${countLabel(knowledgeBase.document_count, 'document')} are ready to investigate.`
}

type OverviewSectionProps = {
  knowledgeBase: KnowledgeBaseSummaryResponse
  activeDomainName: string | null
}

type Handoff = { label: string; to: string }

export function OverviewSection({ activeDomainName, knowledgeBase }: OverviewSectionProps) {
  const scope = `?kb=${encodeURIComponent(knowledgeBase.id)}`
  const handoffs: Handoff[] = [
    { label: 'Investigate entities', to: `/investigation${scope}` },
    { label: 'Review alerts', to: `/alerts${scope}` },
    { label: 'Ask in RAG chat', to: `/rag-chat${scope}` },
  ]
  const handoffsAvailable = knowledgeBase.entity_count > 0
  const kbDomain = knowledgeBase.domain ?? null
  const hasDomainMismatch = isDomainMismatch(kbDomain, activeDomainName)

  return (
    <Card>
      <section aria-labelledby="kb-overview-title" className="kb-overview">
        <h2 id="kb-overview-title">Where this knowledge base stands</h2>
        <p className="page-copy-block">{knowledgeBaseSituation(knowledgeBase)}</p>

        {hasDomainMismatch ? (
          <p className="page-copy-block" data-testid="kb-domain-mismatch-note" role="status">
            This knowledge base was created under the &quot;{kbDomain}&quot; domain, but
            &quot;{activeDomainName}&quot; is now active. Its entities and relationships may
            not match the active domain&apos;s configuration. All actions remain available.
          </p>
        ) : null}

        <div className="kb-overview__actions">
          <Link
            className="page-button page-button--primary"
            to={knowledgeBaseWorkspacePath(knowledgeBase.id, 'add')}
          >
            Add data
          </Link>
          {handoffs.map((handoff) =>
            handoffsAvailable ? (
              <Link
                className="page-button page-button--secondary"
                key={handoff.label}
                to={handoff.to}
              >
                {handoff.label}
              </Link>
            ) : (
              // A disabled destination is a button, not a link: there is
              // nowhere to go. Its reason renders below, not in a tooltip.
              <button
                className="page-button page-button--secondary"
                disabled
                key={handoff.label}
                type="button"
              >
                {handoff.label}
              </button>
            ),
          )}
        </div>

        {handoffsAvailable ? null : (
          <p className="page-copy-block">
            Investigating needs at least one extracted entity.
          </p>
        )}
      </section>
    </Card>
  )
}
```

Add to the CSS file that holds `.kb-settings__details`:

```css
.kb-overview,
.kb-overview__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kb-overview {
  flex-direction: column;
  gap: 12px;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd chili_app && npm run test:run -- src/features/kb/overview/__tests__/OverviewSection.test.tsx`
Expected: PASS, 7 cases.

- [ ] **Step 5: Point the manager page at it, run the suite, commit**

Replace `NextActionsPanel` (and its `navigate`-based handlers, `activeKnowledgeBaseSearch`, `knowledgeBaseSearch`, `submissionAccepted`) with `{knowledgeBase ? <OverviewSection activeDomainName={activeDomainName} knowledgeBase={knowledgeBase} /> : null}`.

```bash
cd chili_app && npm run test:run && npm run lint && npm run build
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "feat(kb): add the workspace overview section"
```

---

### Task 9: Cutover — Library at `/knowledge-bases`, Workspace at `/knowledge-bases/:kbId`

The five sections exist and are tested. This task builds the two pages that host them, wires the routes, and deletes the page they were carved out of.

**Files:**
- Create: `chili_app/src/features/kb/kb.css`
- Create: `chili_app/src/features/kb/WorkspaceTabs.tsx`
- Create: `chili_app/src/features/kb/library/KnowledgeBaseCardList.tsx`
- Create: `chili_app/src/features/kb/library/CreateKnowledgeBasePanel.tsx`
- Create: `chili_app/src/pages/KnowledgeBaseLibraryPage.tsx`
- Create: `chili_app/src/pages/KnowledgeBaseWorkspacePage.tsx`
- Create: `chili_app/src/pages/__tests__/KnowledgeBaseLibraryPage.test.tsx`
- Create: `chili_app/src/pages/__tests__/KnowledgeBaseWorkspacePage.test.tsx`
- Delete: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`
- Delete: `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`
- Delete: `chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx`
- Delete: `chili_app/src/components/ingestion/__tests__/KnowledgeBaseSelector.test.tsx`
- Modify: `chili_app/src/app/router.tsx`
- Modify: `chili_app/src/app/__tests__/router-routes.test.tsx`
- Modify: `chili_app/src/pages/pages.css` (move `.kb-*` rules into `kb.css`; delete `.ingestion-studio-*` and `.ingestion-kb-*` rules with no remaining consumer)

**Interfaces:**
- Consumes: everything from tasks 1–8.
- Produces:
  - `WorkspaceTabs` — props `{ knowledgeBaseId: string }`; renders a `<nav>` of `NavLink`s over `WORKSPACE_SECTIONS`.
  - `KnowledgeBaseCardList` — props `{ activeDomainName: string | null; hiddenDomainCount: number; knowledgeBases: KnowledgeBaseSummaryResponse[]; onToggleShowAllDomains: () => void; showAllDomains: boolean }`. Each card is a `Link` to that KB's overview.
  - `CreateKnowledgeBasePanel` — props `{ onCreated: (knowledgeBaseId: string) => void }`; owns its own name/description state and the create mutation.
  - `KnowledgeBaseLibraryPage`, `KnowledgeBaseWorkspacePage` — no props; routed.

- [ ] **Step 1: Write the failing route test**

Replace `chili_app/src/app/__tests__/router-routes.test.tsx`'s body with assertions over the route table. Read the existing file first and keep its import style; it currently asserts the flat route list. Add:

```ts
import { describe, expect, it } from 'vitest'

import { router } from '../router'

function paths(): string[] {
  const shell = router.routes.find((route) => route.path === '/')
  const children = shell?.children ?? []
  return children.flatMap((child) => {
    const nested = (child.children ?? []).map((grandchild) =>
      grandchild.index ? `${child.path}#index` : `${child.path}/${grandchild.path}`,
    )
    return [child.path ?? '#index', ...nested]
  })
}

describe('router', () => {
  it('serves the library and each workspace section', () => {
    expect(paths()).toEqual(
      expect.arrayContaining([
        'knowledge-bases',
        'knowledge-bases/:kbId#index',
        'knowledge-bases/:kbId/add',
        'knowledge-bases/:kbId/data',
        'knowledge-bases/:kbId/runs',
        'knowledge-bases/:kbId/settings',
      ]),
    )
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/app/__tests__/router-routes.test.tsx`
Expected: FAIL — only `knowledge-bases` is present.

- [ ] **Step 3: Write `WorkspaceTabs`**

```tsx
// chili_app/src/features/kb/WorkspaceTabs.tsx
import { NavLink } from 'react-router'

import { knowledgeBaseWorkspacePath, WORKSPACE_SECTIONS } from '../../utils/knowledgeBaseRoutes'
import type { WorkspaceSection } from '../../utils/knowledgeBaseRoutes'
import './kb.css'

const SECTION_LABELS: Record<WorkspaceSection, string> = {
  overview: 'Overview',
  add: 'Add data',
  data: 'Data',
  runs: 'Runs',
  settings: 'Settings',
}

type WorkspaceTabsProps = {
  knowledgeBaseId: string
}

/**
 * Section navigation as links, not buttons.
 *
 * Each section is a real address, so the tabs must be openable in a new tab,
 * copyable, and reachable by the browser's own back button — which a
 * `role="tablist"` of buttons is not.
 */
export function WorkspaceTabs({ knowledgeBaseId }: WorkspaceTabsProps) {
  return (
    <nav aria-label="Knowledge base sections" className="kb-workspace__tabs">
      {WORKSPACE_SECTIONS.map((section) => (
        <NavLink
          className={({ isActive }) =>
            isActive ? 'tabs__button tabs__button--active' : 'tabs__button'
          }
          end={section === 'overview'}
          key={section}
          to={knowledgeBaseWorkspacePath(knowledgeBaseId, section)}
        >
          {SECTION_LABELS[section]}
        </NavLink>
      ))}
    </nav>
  )
}
```

`end` is set only for overview: without it the overview link would read as active on every section, since every section path starts with the overview path.

- [ ] **Step 4: Write the library page and its parts**

`KnowledgeBaseCardList.tsx` — lift the list body of `KnowledgeBaseSelector` (its header chip, domain toggle, `EmptyState` branches) and turn each list item into a `Link`:

```tsx
              <Link
                className="page-list-item kb-library__card"
                key={knowledgeBase.id}
                to={knowledgeBaseWorkspacePath(knowledgeBase.id)}
              >
                <span className="kb-library__name">{knowledgeBase.name}</span>
                <span className="kb-library__description">{knowledgeBase.description}</span>
                <span className="kb-library__meta">
                  <StatusChip kind="knowledge-base" status={knowledgeBase.status} />
                  <Chip label={countLabel(knowledgeBase.document_count, 'document')} tone="default" />
                  <Chip
                    label={countLabel(knowledgeBase.entity_count, 'entity', 'entities')}
                    tone="network"
                  />
                  <KbDomainBadge
                    activeDomainName={activeDomainName}
                    kbDomain={knowledgeBase.domain ?? null}
                  />
                </span>
                <span className="metric-row__label">
                  Last activity {formatRelativeTime(knowledgeBase.updated_at ?? knowledgeBase.created_at)}
                </span>
              </Link>
```

Keep `data-testid="kb-show-all-domains-toggle"` on the domain toggle and the region label `Choose a knowledge base` on the wrapping `<section aria-labelledby>` heading — both are load-bearing for the e2e suite, and neither name has stopped being accurate.

`CreateKnowledgeBasePanel.tsx` — the create `<form>` from `KnowledgeBaseSelector`, owning `name`/`description` state and `useCreateKnowledgeBase`, wrapped in a `<details>` so it is a "New knowledge base" affordance rather than a permanent form:

```tsx
    <details className="kb-library__create">
      <summary className="page-button page-button--primary">New knowledge base</summary>
      <form onSubmit={handleSubmit}>{/* …name, description, submit… */}</form>
    </details>
```

On success call `onCreated(created.id)`.

`KnowledgeBaseLibraryPage.tsx`:

```tsx
export function KnowledgeBaseLibraryPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [showAllDomains, setShowAllDomains] = useState(false)
  const knowledgeBasesQuery = useKnowledgeBases()
  const domainConfigQuery = useDomainConfig()

  // A pre-split address (`?kb=`, optionally `&document=`) still names a real
  // destination; send it there rather than growing a second way to select.
  const legacyTarget = legacyWorkspaceRedirect(searchParams)
  if (legacyTarget !== null) {
    return <Navigate replace to={legacyTarget} />
  }

  if (knowledgeBasesQuery.isLoading || domainConfigQuery.isLoading) {
    return <LoadingState label="Loading knowledge bases" />
  }
  if (knowledgeBasesQuery.isError || domainConfigQuery.isError) {
    return (
      <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
    )
  }

  // Domain scoping, lifted from the manager page unchanged: KBs stamped with
  // the active domain, plus legacy KBs with no stamp at all. Warn-only — the
  // toggle reveals the rest rather than the scoping being enforced.
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const activeDomainName = domainConfigQuery.data?.domain.name ?? null
  const scopedKnowledgeBases = knowledgeBases.filter(
    (item) => !isDomainMismatch(item.domain ?? null, activeDomainName),
  )
  const hiddenDomainCount = knowledgeBases.length - scopedKnowledgeBases.length
  const visibleKnowledgeBases = showAllDomains ? knowledgeBases : scopedKnowledgeBases

  return (
    <section className="page-grid">
      <SectionHeader
        eyebrow="Ingestion"
        subtitle="Pick a knowledge base to work in, or create one."
        title="Knowledge Bases"
      />
      <Card>
        <CreateKnowledgeBasePanel
          onCreated={(id) => navigate(knowledgeBaseWorkspacePath(id, 'add'))}
        />
      </Card>
      <Card>
        <KnowledgeBaseCardList
          activeDomainName={activeDomainName}
          hiddenDomainCount={hiddenDomainCount}
          knowledgeBases={visibleKnowledgeBases}
          onToggleShowAllDomains={() => setShowAllDomains((value) => !value)}
          showAllDomains={showAllDomains}
        />
      </Card>
    </section>
  )
}
```

Creating lands in Add data, per spec §1 — a brand-new corpus has nothing to look at anywhere else.

- [ ] **Step 5: Write the workspace page**

```tsx
// chili_app/src/pages/KnowledgeBaseWorkspacePage.tsx
import { Outlet, useParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import { useKnowledgeBase } from '../api/knowledgebases'
import { KbDomainBadge } from '../components/knowledgebase/KbDomainBadge'
import { StatusChip } from '../components/status/StatusChip'
import { Chip } from '../components/ui/Chip'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { WorkspaceTabs } from '../features/kb/WorkspaceTabs'
import { countLabel } from '../utils/countLabel'
import '../features/kb/kb.css'

export function KnowledgeBaseWorkspacePage() {
  const { kbId } = useParams<'kbId'>()
  const knowledgeBaseQuery = useKnowledgeBase(kbId ?? null)
  const domainConfigQuery = useDomainConfig()

  if (!kbId) {
    return <ErrorState description="This address does not name a knowledge base." />
  }
  if (knowledgeBaseQuery.isLoading) {
    return <LoadingState label="Loading knowledge base" />
  }
  if (knowledgeBaseQuery.isError || !knowledgeBaseQuery.data) {
    // A deleted or mistyped id: say so and offer the library, rather than
    // silently swapping in a different corpus.
    return (
      <ErrorState description="This knowledge base could not be opened. It may have been deleted. Return to the library to pick another." />
    )
  }

  const knowledgeBase = knowledgeBaseQuery.data
  const activeDomainName = domainConfigQuery.data?.domain.name ?? null

  return (
    <section className="page-grid">
      <header className="kb-workspace__header">
        <div className="kb-workspace__identity">
          <h1>{knowledgeBase.name}</h1>
          <p className="page-copy-block">{knowledgeBase.description}</p>
        </div>
        <div className="kb-workspace__digest">
          <StatusChip kind="knowledge-base" status={knowledgeBase.status} />
          <Chip label={countLabel(knowledgeBase.document_count, 'document')} tone="default" />
          <Chip
            label={countLabel(knowledgeBase.entity_count, 'entity', 'entities')}
            tone="network"
          />
          <KbDomainBadge
            activeDomainName={activeDomainName}
            kbDomain={knowledgeBase.domain ?? null}
          />
        </div>
      </header>
      <WorkspaceTabs knowledgeBaseId={kbId} />
      <Outlet context={{ knowledgeBase, activeDomainName }} />
    </section>
  )
}

export type WorkspaceOutletContext = {
  knowledgeBase: KnowledgeBaseSummaryResponse
  activeDomainName: string | null
}
```

(`import type { KnowledgeBaseSummaryResponse } from '../api/contracts'` — it is the type `GET /knowledgebases/{id}` returns; there is no separate detail contract.)

Each section route reads the loaded knowledge base via `useOutletContext<WorkspaceOutletContext>()` rather than re-fetching it. Create thin route components alongside the sections (in the same files) that do this — for example:

```tsx
// at the bottom of features/kb/runs/RunsSection.tsx
export function RunsRoute() {
  const { knowledgeBase } = useOutletContext<WorkspaceOutletContext>()
  return <RunsSection knowledgeBaseId={knowledgeBase.id} entityCount={knowledgeBase.entity_count} />
}
```

Do the same for `OverviewRoute`, `AddDataRoute` (whose `onSubmitted` navigates to `knowledgeBaseWorkspacePath(id, 'runs')`), `DataRoute` (whose `onStageSource` navigates to `…'add'`), and `SettingsRoute` (whose `onDeleted` navigates to `KNOWLEDGE_BASES_ROUTE`).

- [ ] **Step 6: Wire the routes**

In `chili_app/src/app/router.tsx`, replace the two knowledge-base entries with:

```tsx
      { path: 'knowledge-bases', element: withPageBoundary(<KnowledgeBaseLibraryPage />) },
      {
        path: 'knowledge-bases/:kbId',
        element: withPageBoundary(<KnowledgeBaseWorkspacePage />),
        children: [
          { index: true, element: <OverviewRoute /> },
          { path: 'add', element: <AddDataRoute /> },
          { path: 'data', element: <DataRoute /> },
          { path: 'runs', element: <RunsRoute /> },
          { path: 'settings', element: <SettingsRoute /> },
        ],
      },
      // The legacy address kept its query string, which carried the knowledge
      // base: dropping it sent every old bookmark to an arbitrary corpus.
      { path: 'knowledgebases', element: <LegacyKnowledgeBasesRedirect /> },
```

with

```tsx
function LegacyKnowledgeBasesRedirect() {
  const { search } = useLocation()
  return <Navigate replace to={`${KNOWLEDGE_BASES_ROUTE}${search}`} />
}
```

defined above `router` in the same file. `KnowledgeBaseLibraryPage` then applies `legacyWorkspaceRedirect` to that search string, so `/knowledgebases?kb=X` reaches the workspace in two hops without either hop needing to know about the other.

- [ ] **Step 7: Write the page tests**

Both files share this fixture and fetch stub — write it once per file:

```tsx
const medicareKb = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: 'Active corpus',
  status: 'ready',
  document_count: 8,
  entity_count: 53,
  relationship_count: 21,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
  domain: 'medicare_fraud',
}

const housingKb = {
  ...medicareKb,
  id: 'kb-2',
  name: 'Housing KB',
  description: 'Another domain',
  domain: 'department_air_force_housing',
}

const domainConfig = {
  domain: { name: 'medicare_fraud', display_name: 'Medicare Fraud', description: '' },
  entities: [],
  relationships: [],
  capabilities: {
    timeseries: true,
    gnn: true,
    risk_scoring: true,
    rag_chat: true,
    explainability: true,
    structured_ingestion: true,
  },
  ingestion: {},
  validation: {
    max_file_size_mb: 50,
    allowed_content_types: ['text/plain'],
    max_query_length: 10000,
    max_rag_question_length: 5000,
  },
  records: { feeds: [] },
  alerts: { thresholds: {} },
}

const originalFetch = globalThis.fetch

beforeEach(() => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    const json = (payload: unknown) =>
      new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })

    if (url.endsWith('/config/domain')) return json(domainConfig)
    if (url.endsWith('/knowledgebases')) return json({ items: [medicareKb, housingKb], total: 2 })
    if (url.endsWith('/knowledgebases/kb-1')) return json(medicareKb)
    if (url.endsWith('/knowledgebases/kb-missing')) {
      return new Response(JSON.stringify({ detail: 'not found' }), { status: 404 })
    }
    if (url.includes('/documents')) return json({ items: [], total: 0 })
    if (url.includes('/workflows')) return json({ items: [], total: 0 })
    if (url.includes('/score-runs')) return json({ items: [], total: 0 })
    throw new Error(`unexpected request: ${url}`)
  }) as unknown as typeof fetch
})

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.restoreAllMocks()
})

function renderAt(initialEntry: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const testRouter = createMemoryRouter(
    [
      { path: '/knowledge-bases', element: <KnowledgeBaseLibraryPage /> },
      {
        path: '/knowledge-bases/:kbId',
        element: <KnowledgeBaseWorkspacePage />,
        children: [
          { index: true, element: <p>Overview body</p> },
          { path: 'add', element: <p>Add body</p> },
          { path: 'data', element: <p>Data body</p> },
          { path: 'runs', element: <p>Runs body</p> },
          { path: 'settings', element: <p>Settings body</p> },
        ],
      },
    ],
    { initialEntries: [initialEntry] },
  )

  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={testRouter} />
    </QueryClientProvider>,
  )
  return testRouter
}
```

`KnowledgeBaseLibraryPage.test.tsx`:

```tsx
describe('KnowledgeBaseLibraryPage', () => {
  it('links each card to that knowledge base’s workspace', async () => {
    renderAt('/knowledge-bases')

    const card = await screen.findByRole('link', { name: /Fraud KB/ })
    expect(card).toHaveAttribute('href', '/knowledge-bases/kb-1')
  })

  it('scopes to the active domain and reveals the rest on demand', async () => {
    renderAt('/knowledge-bases')

    await waitFor(() => expect(screen.getByText('Fraud KB')).toBeInTheDocument())
    expect(screen.queryByText('Housing KB')).not.toBeInTheDocument()

    await userEvent.click(screen.getByTestId('kb-show-all-domains-toggle'))
    expect(screen.getByText('Housing KB')).toBeInTheDocument()
  })

  it('redirects a legacy ?kb= address to that workspace', async () => {
    const testRouter = renderAt('/knowledge-bases?kb=kb-1')

    await waitFor(() => {
      expect(testRouter.state.location.pathname).toBe('/knowledge-bases/kb-1')
    })
  })

  it('redirects a legacy ?kb=&document= address into the data section', async () => {
    const testRouter = renderAt('/knowledge-bases?kb=kb-1&document=doc-2')

    await waitFor(() => {
      expect(testRouter.state.location.pathname).toBe('/knowledge-bases/kb-1/data')
      expect(testRouter.state.location.search).toBe('?document=doc-2')
    })
  })
})
```

`KnowledgeBaseWorkspacePage.test.tsx`:

```tsx
describe('KnowledgeBaseWorkspacePage', () => {
  it('names the knowledge base and states its digest', async () => {
    renderAt('/knowledge-bases/kb-1')

    expect(await screen.findByRole('heading', { level: 1, name: 'Fraud KB' })).toBeInTheDocument()
    expect(screen.getByText('8 documents')).toBeInTheDocument()
    expect(screen.getByText('53 entities')).toBeInTheDocument()
  })

  it('offers every section as a link', async () => {
    renderAt('/knowledge-bases/kb-1')

    const tabs = await screen.findByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Overview' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1',
    )
    expect(within(tabs).getByRole('link', { name: 'Add data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/add',
    )
    expect(within(tabs).getByRole('link', { name: 'Data' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/data',
    )
    expect(within(tabs).getByRole('link', { name: 'Runs' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/runs',
    )
    expect(within(tabs).getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/knowledge-bases/kb-1/settings',
    )
  })

  it('marks only the section on screen as current', async () => {
    renderAt('/knowledge-bases/kb-1/runs')

    const tabs = await screen.findByRole('navigation', { name: 'Knowledge base sections' })
    expect(within(tabs).getByRole('link', { name: 'Runs' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    // Without `end`, Overview would read as current on every section, because
    // every section path starts with the overview path.
    expect(within(tabs).getByRole('link', { name: 'Overview' })).not.toHaveAttribute(
      'aria-current',
    )
  })

  it('renders the section body for the address', async () => {
    renderAt('/knowledge-bases/kb-1/settings')

    expect(await screen.findByText('Settings body')).toBeInTheDocument()
  })

  it('says so for an unknown id instead of showing another knowledge base', async () => {
    renderAt('/knowledge-bases/kb-missing')

    expect(await screen.findByText(/could not be opened/i)).toBeInTheDocument()
    expect(screen.queryByText('Fraud KB')).not.toBeInTheDocument()
  })
})
```

Imports for both files: `QueryClient, QueryClientProvider` from `@tanstack/react-query`; `render, screen, waitFor, within` from `@testing-library/react`; `userEvent` from `@testing-library/user-event`; `createMemoryRouter, RouterProvider` from `react-router`; `afterEach, beforeEach, describe, expect, it, vi` from `vitest`.

- [ ] **Step 8: Delete the old page**

```bash
cd /home/rhagan/chiliAI
git rm chili_app/src/pages/KnowledgeBaseManagerPage.tsx \
       chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx \
       chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx \
       chili_app/src/components/ingestion/__tests__/KnowledgeBaseSelector.test.tsx
```

Before deleting the 1372-line test file, read it once more and confirm every behaviour it asserted now has a home in `DataSection`, `AddDataSection`, `RunsSection`, `SettingsSection`, `OverviewSection`, `KnowledgeBaseLibraryPage` or `KnowledgeBaseWorkspacePage` tests. Anything with no home is a gap — write the test where it belongs before deleting.

Then move the `.kb-*` rules from `pages.css` into `chili_app/src/features/kb/kb.css`, add the workspace header/tab rules, and delete every `.ingestion-studio-*` and `.ingestion-kb-*` rule that no longer has a consumer (`grep -rn` each class name before deleting it).

```css
/* chili_app/src/features/kb/kb.css */
.kb-workspace__header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.kb-workspace__digest,
.kb-workspace__tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.kb-library {
  display: grid;
  gap: 12px;
}

@container workspace (min-width: 720px) {
  .kb-library {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }
}

.kb-library__card {
  display: grid;
  gap: 6px;
  text-decoration: none;
}
```

- [ ] **Step 9: Run everything and commit**

Run: `cd chili_app && npm run test:run && npm run lint && npm run build`
Expected: green. `npm run build` is the check that no dangling import to the deleted page survives.

```bash
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "feat(kb): split knowledge bases into a library and a per-KB workspace"
```

---

### Task 10: Staged work is not lost by navigating away

The only place in this flow where work can be destroyed silently is leaving Add data with files staged. One prompt, once (spec §6).

**Files:**
- Modify: `chili_app/src/features/kb/add-data/AddDataSection.tsx`
- Modify: `chili_app/src/features/kb/add-data/__tests__/AddDataSection.test.tsx`

**Interfaces:**
- Consumes: `hasStagedWork` (Task 3), `ConfirmDialog` (phase 1), `useBlocker` (react-router 8).

- [ ] **Step 1: Write the failing test**

Append to `AddDataSection.test.tsx`. This case needs a real data router, so add a second render helper:

```tsx
import { createMemoryRouter, Link, RouterProvider } from 'react-router'

function renderInRouter() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createMemoryRouter(
    [
      {
        path: '/knowledge-bases/kb-1/add',
        element: (
          <>
            <AddDataSection knowledgeBaseId="kb-1" onSubmitted={vi.fn()} />
            <Link to="/knowledge-bases/kb-1/runs">Go to runs</Link>
          </>
        ),
      },
      { path: '/knowledge-bases/kb-1/runs', element: <p>Runs section</p> },
    ],
    { initialEntries: ['/knowledge-bases/kb-1/add'] },
  )

  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return router
}
```

```tsx
  it('asks before discarding staged files on the way out', async () => {
    renderInRouter()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['{}'], 'claim.json', { type: 'application/json' }),
    )
    await userEvent.click(screen.getByRole('link', { name: 'Go to runs' }))

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent('Discard staged files for this knowledge base?')
    expect(screen.queryByText('Runs section')).not.toBeInTheDocument()

    await userEvent.click(within(dialog).getByRole('button', { name: 'Keep staging' }))
    expect(screen.getByLabelText('Document files', { exact: true })).toBeInTheDocument()
  })

  it('lets the navigation through once discarding is confirmed', async () => {
    renderInRouter()

    await userEvent.click(await screen.findByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files', { exact: true }),
      new File(['{}'], 'claim.json', { type: 'application/json' }),
    )
    await userEvent.click(screen.getByRole('link', { name: 'Go to runs' }))

    const dialog = await screen.findByRole('dialog')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Discard' }))

    await waitFor(() => {
      expect(screen.getByText('Runs section')).toBeInTheDocument()
    })
  })

  it('does not ask when there is nothing staged', async () => {
    renderInRouter()

    await userEvent.click(screen.getByRole('link', { name: 'Go to runs' }))

    await waitFor(() => {
      expect(screen.getByText('Runs section')).toBeInTheDocument()
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/features/kb/add-data/__tests__/AddDataSection.test.tsx`
Expected: FAIL — the navigation goes straight through; no dialog appears.

- [ ] **Step 3: Implement the blocker**

In `AddDataSection.tsx`:

```tsx
import { useBlocker } from 'react-router'

import { hasStagedWork } from '../../../stores/ingestionDraftStore'
```

```tsx
  const staged = hasStagedWork(draft)
  // The only place in this flow where leaving loses work. A submitted draft is
  // cleared before this can fire, so the prompt never appears after a success.
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      staged && currentLocation.pathname !== nextLocation.pathname,
  )
```

and render, alongside the two cards:

```tsx
      <ConfirmDialog
        body="The files and rows staged here have not been submitted. Leaving discards them."
        cancelLabel="Keep staging"
        confirmLabel="Discard"
        destructive
        onCancel={() => blocker.reset?.()}
        onConfirm={() => {
          clearDraft(knowledgeBaseId)
          blocker.proceed?.()
        }}
        open={blocker.state === 'blocked'}
        title="Discard staged files for this knowledge base?"
      />
```

`ConfirmDialog` currently hardcodes its cancel label. Add an optional `cancelLabel?: string` prop defaulting to `'Cancel'` and use it — check `chili_app/src/components/status/ConfirmDialog.tsx` and update its test to cover the new prop.

`useBlocker` only intercepts in-app navigation. That is the honest limit: a hard reload or a closed tab still discards staging, and no `beforeunload` handler is added, because a browser-chrome confirmation the app cannot word is worse than none.

- [ ] **Step 4: Run the test, lint, commit**

Run: `cd chili_app && npm run test:run && npm run lint && npm run build`
Expected: PASS, 6 cases in `AddDataSection.test.tsx`.

```bash
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "feat(kb): confirm before discarding staged ingestion work"
```

---

### Task 11: Point every internal link at the workspace

The redirect keeps old bookmarks working. Links the app emits today should not need it.

**Files:**
- Modify: `chili_app/src/lib/citationTargets.ts`
- Modify: `chili_app/src/lib/__tests__/citationTargets.test.ts`
- Modify: `chili_app/src/components/knowledgebase/EmptyKnowledgeBaseNotice.tsx`
- Modify: `chili_app/src/pages/PolicyIntelligencePage.tsx`
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Modify: `chili_app/src/pages/RagChatPage.tsx`
- Modify: `chili_app/src/pages/DashboardPage.tsx`
- Modify: the corresponding page tests where they assert on these hrefs

**Interfaces:**
- Consumes: `knowledgeBaseWorkspacePath` (Task 1).

- [ ] **Step 1: Write the failing citation test**

In `chili_app/src/lib/__tests__/citationTargets.test.ts`, change the two expected document-citation `to` values:

```ts
    expect(target).toEqual(
      expect.objectContaining({
        kind: 'link',
        to: '/knowledge-bases/kb-1/data?document=doc-7',
      }),
    )
```

and, for the citation carrying a chunk:

```ts
        to: '/knowledge-bases/kb-1/data?document=doc-7&chunk=3',
```

Read the file first and edit the existing expectations rather than adding new cases — there should be exactly one assertion per document-citation path.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd chili_app && npm run test:run -- src/lib/__tests__/citationTargets.test.ts`
Expected: FAIL — received `/knowledge-bases?kb=kb-1&document=doc-7`.

- [ ] **Step 3: Update the link builders**

In `citationTargets.ts`, replace both `/knowledge-bases${query([['kb', …], ['document', …], …])}` constructions with:

```ts
      to: `${knowledgeBaseWorkspacePath(knowledgeBaseId, 'data')}${query([
        ['document', documentId],
      ])}`,
```

(and the second one carrying `['chunk', citation.chunk_index]` as well). Import `knowledgeBaseWorkspacePath` from `../utils/knowledgeBaseRoutes`. The existing `query()` helper already skips null/undefined values — keep using it.

- [ ] **Step 4: Update the remaining four call sites**

- `EmptyKnowledgeBaseNotice.tsx`: `to={knowledgeBaseWorkspacePath(knowledgeBase.id, 'add')}` — the notice exists because the knowledge base is empty, so Add data is where it should land.
- `PolicyIntelligencePage.tsx:236`: `to={knowledgeBaseWorkspacePath(knowledgeBaseId)}`.
- `InvestigationWorkbenchPage.tsx:925`: `to={activeKnowledgeBaseId ? knowledgeBaseWorkspacePath(activeKnowledgeBaseId) : KNOWLEDGE_BASES_ROUTE}` — the old code interpolated an empty string when there was no active KB, producing `?kb=`, which the library would then have tried to redirect on.
- `InvestigationWorkbenchPage.tsx:560` and `RagChatPage.tsx:156`: `navigate('/knowledge-bases')` → `navigate(KNOWLEDGE_BASES_ROUTE)`. These are "go pick a knowledge base" prompts; the library is the right destination.
- `DashboardPage.tsx:245`: the "Workflow runs" KPI card links to the whole page today. Point it at the active knowledge base's runs when there is one: `to={activeKnowledgeBaseId ? knowledgeBaseWorkspacePath(activeKnowledgeBaseId, 'runs') : KNOWLEDGE_BASES_ROUTE}`.

- [ ] **Step 5: Run the suite, fix the page tests it surfaces, commit**

Run: `cd chili_app && npm run test:run && npm run lint && npm run build`
Expected: `DashboardPage.test.tsx`, `PolicyIntelligencePage.test.tsx`, `InvestigationWorkbenchPage.test.tsx` and `RagChatPage.test.tsx` may assert on the old hrefs — update the expectations to the new paths.

```bash
cd /home/rhagan/chiliAI && git add -A chili_app/src
git commit -m "refactor(kb): link internal destinations at the workspace routes"
```

---

### Task 12: Delete the orphaned knowledgebase component cluster

Seven components with no consumer but each other, kept alive by their own tests. The spec calls for their removal now that the pattern they anticipated exists for real (spec §1 "Deletions").

**On the salvage note.** §1 asks that `DropZone`'s drag-drop and input-reset semantics inform §2 staging before it is deleted. The input-reset and append half landed in phase 1's `DocumentSourcePanel`. The drag-drop half does not exist anywhere live — `DropZone` has no consumer and never had one — so deleting it removes no working capability and regresses nothing. Drag-to-stage remains owed to §2; record it in this task's commit body so it is not lost with the file.

**Files:**
- Delete: `chili_app/src/components/knowledgebase/{KbTable.tsx,KbTable.module.css,KbDetailView.tsx,CreateKbForm.tsx,DropZone.tsx,DropZone.module.css,DocumentTable.tsx,StatusBadge.tsx,UploadProgress.tsx}`
- Delete: `chili_app/src/components/knowledgebase/__tests__/{KbTable.test.tsx,CreateKbForm.test.tsx,DropZone.test.tsx,StatusBadge.test.tsx}`

- [ ] **Step 1: Prove they are orphaned**

```bash
cd /home/rhagan/chiliAI/chili_app/src
for c in KbTable KbDetailView CreateKbForm DropZone DocumentTable StatusBadge; do
  echo "--- $c"
  grep -rn "knowledgebase/$c\|from './$c'\|from '../$c'" . --include=*.ts --include=*.tsx
done
grep -rn "knowledgebase/UploadProgress" . --include=*.ts --include=*.tsx
```

Expected: every hit is inside `components/knowledgebase/` itself or its `__tests__`. If anything outside those two places references one, stop and re-check — that component is live and must not be deleted.

`EmptyKnowledgeBaseNotice`, `KbDomainBadge`, `ScoreRunStatusPanel` and `domainMismatch.ts` are live. Do not touch them.

- [ ] **Step 2: Delete them**

```bash
cd /home/rhagan/chiliAI
git rm chili_app/src/components/knowledgebase/KbTable.tsx \
       chili_app/src/components/knowledgebase/KbTable.module.css \
       chili_app/src/components/knowledgebase/KbDetailView.tsx \
       chili_app/src/components/knowledgebase/CreateKbForm.tsx \
       chili_app/src/components/knowledgebase/DropZone.tsx \
       chili_app/src/components/knowledgebase/DropZone.module.css \
       chili_app/src/components/knowledgebase/DocumentTable.tsx \
       chili_app/src/components/knowledgebase/StatusBadge.tsx \
       chili_app/src/components/knowledgebase/UploadProgress.tsx \
       chili_app/src/components/knowledgebase/__tests__/KbTable.test.tsx \
       chili_app/src/components/knowledgebase/__tests__/CreateKbForm.test.tsx \
       chili_app/src/components/knowledgebase/__tests__/DropZone.test.tsx \
       chili_app/src/components/knowledgebase/__tests__/StatusBadge.test.tsx
```

- [ ] **Step 3: Verify nothing depended on them**

Run: `cd chili_app && npm run build && npm run test:run && npm run lint`
Expected: green. `tsc -b` inside `npm run build` is the real proof.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(kb): delete the orphaned knowledgebase component cluster

DropZone's input-reset and append semantics were salvaged into
DocumentSourcePanel in phase 1. Its drag-to-stage half was never wired to
anything, so nothing regresses here — but §2 of the design spec still asks for
a drop zone on document staging, and that is now owed with no code left to
salvage it from."
```

---

### Task 13: End-to-end verification, docs, and the phase gate

The suite is the only thing that has been running against the real stack. Bring it in line with the new addresses, add coverage for what this phase actually changed, and leave the documentation telling the truth.

**Files:**
- Create: `chili_app/e2e/kb-workspace-navigation.spec.ts`
- Modify: `chili_app/e2e/knowledge-base-list.spec.ts`
- Modify: `chili_app/e2e/ingestion-studio-domain-scoping.spec.ts`
- Modify: `chili_app/e2e/ingestion-records.spec.ts`
- Modify: `chili_app/e2e/ingestion-document-warnings.spec.ts`
- Modify: `chili_app/e2e/ingestion-truth-safety.spec.ts`
- Modify: `chili_app/e2e/kb-domain-mismatch.spec.ts`
- Modify: `chili_app/e2e/citation-navigation.spec.ts` (if it asserts on the KB URL)
- Modify: `chili_app/e2e/layout-overflow.spec.ts` (add the new routes to whatever route list it sweeps)
- Modify: `chili_app/README.md`, `docs/architecture.md`, `.github/copilot-instructions.md`

- [ ] **Step 1: Write the new navigation spec**

```ts
// chili_app/e2e/kb-workspace-navigation.spec.ts
/**
 * Knowledge Bases IA (full stack).
 *
 * The split's whole claim is that the URL owns which knowledge base and which
 * stage you are looking at. These assertions are that claim: a section is
 * addressable, a reload keeps it, the top-bar picker moves between workspaces
 * without changing section, and every pre-split address still lands somewhere
 * correct. No API mocking.
 */
import { expect, test } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

let seededKbId: string
let seededKbName: string

test.beforeAll(async () => {
  const response = await fetch(`${API}/knowledgebases`)
  if (!response.ok) {
    throw new Error(`GET /knowledgebases failed (${response.status})`)
  }
  const items = ((await response.json()) as {
    items: Array<{ id: string; name: string }>
  }).items
  const seeded = items.find((item) => item.name === 'E2E Seed KB') ?? items[0]
  if (!seeded) {
    throw new Error('no knowledge base available for the workspace navigation spec')
  }
  seededKbId = seeded.id
  seededKbName = seeded.name
})

test.describe('Knowledge base workspace navigation', () => {
  test('a library card opens that knowledge base’s workspace', async ({ page }) => {
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()

    await page
      .getByRole('region', { name: 'Choose a knowledge base' })
      .getByRole('link', { name: new RegExp(seededKbName) })
      .first()
      .click()

    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${seededKbId}$`))
    await expect(page.getByRole('heading', { level: 1, name: seededKbName })).toBeVisible()
  })

  test('each section is a real address that survives a reload', async ({ page }) => {
    for (const section of ['add', 'data', 'runs', 'settings']) {
      await page.goto(`/knowledge-bases/${seededKbId}/${section}`)
      await expect(page.getByRole('heading', { level: 1, name: seededKbName })).toBeVisible()
      await page.reload()
      await expect(page).toHaveURL(new RegExp(`/${section}$`))
      await expect(page.getByRole('heading', { level: 1, name: seededKbName })).toBeVisible()
    }
  })

  test('a legacy ?kb= address redirects to the workspace', async ({ page }) => {
    await page.goto(`/knowledge-bases?kb=${seededKbId}`)
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${seededKbId}$`))
  })

  test('a legacy ?kb=&document= address redirects into the data section', async ({ page }) => {
    await page.goto(`/knowledge-bases?kb=${seededKbId}&document=doc-does-not-exist`)
    await expect(page).toHaveURL(
      new RegExp(`/knowledge-bases/${seededKbId}/data\\?document=doc-does-not-exist$`),
    )
  })

  test('the legacy /knowledgebases path keeps its knowledge base', async ({ page }) => {
    await page.goto(`/knowledgebases?kb=${seededKbId}`)
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${seededKbId}$`))
  })

  test('the top-bar picker moves between workspaces without leaving the section', async ({
    page,
  }) => {
    await page.goto(`/knowledge-bases/${seededKbId}/runs`)
    const picker = page.getByLabel('Active knowledge base')
    const options = await picker.locator('option').all()
    const other = (
      await Promise.all(options.map(async (option) => option.getAttribute('value')))
    ).find((value) => value && value !== seededKbId)

    test.skip(!other, 'needs a second in-domain knowledge base')

    await picker.selectOption(other as string)
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${other}/runs$`))
  })

  test('an unknown knowledge base id says so instead of showing another corpus', async ({
    page,
  }) => {
    await page.goto('/knowledge-bases/kb-does-not-exist')
    await expect(page.getByText(/could not be opened/i)).toBeVisible()
  })
})
```

- [ ] **Step 2: Bring the stack up and run the new spec**

```bash
cd /home/rhagan/chiliAI && make dev    # leave running in another shell
cd chili_app && npx playwright test e2e/kb-workspace-navigation.spec.ts
```

Expected: 7 passed (the picker case may skip on a single-KB stack). Fix the product, not the spec, for anything that fails.

- [ ] **Step 3: Update the existing knowledge-base specs**

- `knowledge-base-list.spec.ts` — the region and heading are unchanged; the KB name is now inside a `<a>` rather than a `<button>`. Change `getByText(...)` to `getByRole('link', { name: … })`.
- `ingestion-studio-domain-scoping.spec.ts` — replace the `.ingestion-kb-list__item` locator with `.kb-library__card` and `.ingestion-kb-selector__header .ui-chip` with whatever the library header renders. Keep `kb-show-all-domains-toggle`. Everything else about the spec's logic (reading the real config and KB list, computing the expected scoped set) stays.
- `ingestion-truth-safety.spec.ts` — the phase-1 regressions all still matter, but each now lives at an address. Rework the helpers:
  - `selectKnowledgeBase(page, name)` becomes `await page.goto(\`/knowledge-bases/${id}/add\`)`; capture the id from the create response or from `page.url()` after creating.
  - The create step moves to `/knowledge-bases` and the `<details>` create panel.
  - The staging, cross-KB-isolation, and submit cases run at `/…/add`; the inventory and zero-entity cases at `/…/data`; the run/receipt cases at `/…/runs`; both deletion cases at `/…/data` and `/…/settings` respectively.
  - Add one assertion to the cross-KB isolation case that the *route* changed, not just the draft: after navigating to the other KB's `/add`, the staged list is empty; navigating back restores it.
- `ingestion-records.spec.ts`, `ingestion-document-warnings.spec.ts`, `kb-domain-mismatch.spec.ts` — retarget their `page.goto('/knowledge-bases')` + click-to-select to a direct workspace URL.
- `layout-overflow.spec.ts` — add `/knowledge-bases/<seeded id>/{add,data,runs,settings}` to the routes it sweeps. Keep the native-`<select>`/`<input>` carve-out comment intact.

- [ ] **Step 4: Run the whole e2e suite**

```bash
cd chili_app && npm run test:e2e
```

Expected: all green. Per CLAUDE.md, a failure you surface here is yours to diagnose and fix, whether or not this phase caused it.

- [ ] **Step 5: Verify against the running app by hand**

With `make dev` up, walk the journey in a browser and confirm each one:
1. `/knowledge-bases` lists cards; creating one lands in that KB's Add data.
2. Staging two documents, then navigating to Runs, prompts to discard; cancelling keeps the staging.
3. Submitting navigates to Runs and the run appears there, with its receipt, and survives a reload.
4. The Data section's `?document=` changes as you select rows, and pasting that URL in a new tab opens the same document.
5. Switching KB in the top bar while on Runs lands on the other KB's Runs.
6. Deleting from Settings returns to the library and the KB is gone.

- [ ] **Step 6: Update the documentation**

- `chili_app/README.md` — replace the `/knowledge-bases` page description with the Library/Workspace split, name the five sections and their routes, note that the stepper and `ingestionStudioStore` are gone and that drafts live in `stores/ingestionDraftStore.ts` keyed by KB id, and record the two redirect behaviours.
- `docs/architecture.md` — update the frontend route table and the store map line (`ingestionStudioStore` → `ingestionDraftStore`); add a sentence that KB selection is URL-owned and that `useActiveKnowledgeBase` reads the route path (UXA-101).
- `.github/copilot-instructions.md` — if it names the knowledge-base page or its store, update it to match.
- Re-read `CLAUDE.md`, every `README.md`, and the non-archived files under `docs/` for statements this phase falsified (search for `ingestion-studio`, `IngestionStepper`, `currentStep`, `ingestionStudioStore`, `?kb=` in a knowledge-base context) and correct each one.

- [ ] **Step 7: Run every gate**

```bash
cd /home/rhagan/chiliAI/chili_app && npm run lint && npm run build && npm run test:run
cd /home/rhagan/chiliAI && git status --short          # expect only intended changes
git diff --stat chili_app/openapi.json                  # expect no output: no backend change this phase
```

Backend gates are unaffected by this phase, but run them once to prove it:

```bash
cd /home/rhagan/chiliAI/backend && .venv/bin/ruff check --no-cache . && .venv/bin/pyright
```

- [ ] **Step 8: Commit**

```bash
cd /home/rhagan/chiliAI && git add -A
git commit -m "test(e2e): move the knowledge-base journeys onto the workspace routes

Also records what phase 2 deliberately left for later: role gating (no shipped
pack declares admin/viewer), the confirm stage with replace warnings (needs the
phase-3 precheck endpoint), the per-activity readiness chip (phase 3), and the
connector card, multi-feed queue and insert-only banner (phase 4)."
```

---

## Done when

- `/knowledge-bases` is a library of cards and nothing else; no staging, no runs, no deletion.
- Each of the five workspace sections is reachable by URL, survives a reload, and is linked by the tabs.
- `?kb=`, `?kb=&document=`, and `/knowledgebases` addresses all still land somewhere correct.
- Selecting a knowledge base in the top bar while inside the area navigates and keeps the section.
- `IngestionStepper`, `currentStep`, `ingestionStudioStore`, `KnowledgeBaseManagerPage`, `KnowledgeBaseSelector` and the seven orphaned `components/knowledgebase/` files are gone from the tree.
- No file in `features/kb/` or `pages/KnowledgeBase*.tsx` exceeds ~300 lines.
- `npm run lint`, `npm run build`, `npm run test:run` and `npm run test:e2e` are all green, and `chili_app/openapi.json` is unchanged.
