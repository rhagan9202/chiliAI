# Theme 3 — Frontend Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the four frontend issues flagged in the review — hardcoded Medicare/Medicaid filter labels in `DashboardPage`, the inert global search input in `TopBar`, the `Date.parse` fallback in `validateIngestion`, and the duplicate `useAlerts` hook with conflicting endpoints.

**Architecture:** All four fixes are scoped to `chili_app/`. The validator fix tightens client-side validation to match the backend's `_coerce_value` accepted formats exactly. The dashboard and topbar fixes apply YAGNI (remove inert UI). The alerts hook consolidation migrates alert-related types and the bare `useAlerts()` consumer onto the existing `api/contracts.ts` + `api/alerts.ts` contract layer; non-alert types in `src/types/api.ts` remain untouched (they're shared by knowledgebase / investigation / entity hooks that aren't in this theme's scope).

**Tech Stack:** React 19, TypeScript strict, Vite 8, TanStack Query, Vitest, Playwright

**Dependencies on other themes:** None. Theme 3 is independent and can ship at any time.

---

## File Structure

**Modify:**
- `chili_app/src/lib/ingestion/validateIngestion.ts` (lines 191-211) — tighten `isValidDateValue` to drop `Date.parse` fallback
- `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts` — add date validator tests
- `chili_app/src/pages/DashboardPage.tsx` (lines 28-32, 36-37, 73) — remove hardcoded filters
- `chili_app/src/components/layout/TopBar.tsx` (lines 27, 31-35) — remove inert search input + scaffold eyebrow
- `chili_app/src/components/alerts/AlertTable.tsx` (line 3) — migrate `Alert` type import
- `chili_app/src/components/alerts/__tests__/AlertTable.test.tsx` — update type import
- `chili_app/src/components/alerts/AlertFilters.tsx` — update type imports if it consumes `Alert`/`AlertSeverity` from `types/api.ts`
- `chili_app/src/types/api.ts` — remove the alert-specific exports (`Alert`, `AlertListResponse`, `AlertSeverity`, `AlertStatus`)

**Delete:**
- `chili_app/src/hooks/useAlerts.ts` — superseded by `chili_app/src/api/alerts.ts`

---

## Pre-Flight Sanity Check (do this once before Task 1)

- [ ] **Baseline test pass**

```bash
cd chili_app && npm run lint 2>&1 | tail -5
cd chili_app && npm run test:run 2>&1 | tail -10
cd chili_app && npm run build 2>&1 | tail -5
```

Expected: all three clean. If anything fails BEFORE your changes, note it and distinguish your-changes failures later.

- [ ] **Confirm the issues exist**

```bash
grep -n "Medicare\|Medicaid" chili_app/src/pages/DashboardPage.tsx
```

Expected: 2 matches at lines 30-31 ("Medicare FFS", "Medicaid").

```bash
grep -n "Production UI foundation\|<input" chili_app/src/components/layout/TopBar.tsx
```

Expected: matches at line 27 (eyebrow text) and line 34 (inert input).

```bash
grep -n "Date.parse" chili_app/src/lib/ingestion/validateIngestion.ts
```

Expected: 2 matches at lines 196 and 210.

```bash
grep -rln "from .*hooks/useAlerts" chili_app/src/
```

Expected: only `chili_app/src/components/alerts/AlertTable.tsx` consumes it (or no matches if AlertTable already migrated). Confirm scope of cleanup.

---

## Task 1: Tighten `isValidDateValue` to drop `Date.parse` fallback

**Files:**
- Modify: `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`
- Modify: `chili_app/src/lib/ingestion/validateIngestion.ts:191-211`

- [ ] **Step 1: Add failing tests**

Append to `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts` inside the existing `describe('ingestion validation', ...)` block (or in a new `describe('isValidDateValue', ...)` block if cleaner). Use the existing `validateRecordRows` flow to indirectly drive the validator if `isValidDateValue` is not exported — and if it isn't exported, EXPORT it from `validateIngestion.ts` for testability (named export).

```typescript
import { describe, expect, it } from 'vitest'
import { isValidDateValue } from '../validateIngestion'

describe('isValidDateValue', () => {
  it('accepts ISO YYYY-MM-DD', () => {
    expect(isValidDateValue('2024-01-15')).toBe(true)
  })

  it('accepts compact YYYYMMDD', () => {
    expect(isValidDateValue('20240115')).toBe(true)
  })

  it('accepts MM/DD/YYYY with single-digit month and day', () => {
    expect(isValidDateValue('1/5/2024')).toBe(true)
  })

  it('accepts MM/DD/YYYY with leading zeros', () => {
    expect(isValidDateValue('01/05/2024')).toBe(true)
  })

  it('rejects ambiguous year-only strings the backend would reject', () => {
    expect(isValidDateValue('2024')).toBe(false)
  })

  it('rejects locale-dependent month-name strings', () => {
    expect(isValidDateValue('Jan 1')).toBe(false)
    expect(isValidDateValue('January 1, 2024')).toBe(false)
  })

  it('rejects ISO-like strings with timezone suffixes the backend rejects', () => {
    expect(isValidDateValue('2024-01-15T10:00:00Z')).toBe(false)
  })

  it('rejects empty strings', () => {
    expect(isValidDateValue('')).toBe(false)
    expect(isValidDateValue('   ')).toBe(false)
  })

  it('rejects malformed digit groupings', () => {
    expect(isValidDateValue('2024011')).toBe(false)
    expect(isValidDateValue('13/40/2024')).toBe(false)
  })
})
```

If `isValidDateValue` is currently a non-exported function in `validateIngestion.ts`, add `export` to its declaration:

```typescript
export function isValidDateValue(value: unknown): boolean {
```

- [ ] **Step 2: Run the new tests and confirm they fail**

```bash
cd chili_app && npx vitest run src/lib/ingestion/__tests__/validateIngestion.test.ts --reporter=verbose
```

Expected: the rejection tests (`'2024'`, `'Jan 1'`, ISO with timezone) FAIL because `Date.parse('2024')` returns a number, `Date.parse('Jan 1')` returns a number in most browser+Node engines, and `Date.parse('2024-01-15T10:00:00Z')` is also valid.

- [ ] **Step 3: Apply the fix**

In `chili_app/src/lib/ingestion/validateIngestion.ts`, replace the `isValidDateValue` function (lines 191-211) with this version:

```typescript
export function isValidDateValue(value: unknown): boolean {
  if (value instanceof Date) {
    return !Number.isNaN(value.getTime())
  }
  if (typeof value !== 'string') {
    return false
  }
  const text = value.trim()
  if (text.length === 0) {
    return false
  }
  // ISO YYYY-MM-DD: the existing primitive validator already enforces this
  // via the schema's `pattern`. The two non-ISO formats below mirror the
  // backend's `_coerce_value` accepted forms exactly.
  const ISO_YMD = /^(\d{4})-(\d{2})-(\d{2})$/
  let match = ISO_YMD.exec(text)
  if (match) {
    return isValidCalendarDate(Number(match[1]), Number(match[2]), Number(match[3]))
  }
  match = YYYYMMDD_RE.exec(text)
  if (match) {
    return isValidCalendarDate(Number(match[1]), Number(match[2]), Number(match[3]))
  }
  match = MM_DD_YYYY_RE.exec(text)
  if (match) {
    return isValidCalendarDate(Number(match[3]), Number(match[1]), Number(match[2]))
  }
  return false
}
```

Key changes:
- Non-string non-Date values: return `false` (was `!Number.isNaN(Date.parse(String(value)))`)
- Final fallback: return `false` (was `!Number.isNaN(Date.parse(text))`)
- Add explicit `ISO_YMD` match so the function is self-contained (backend accepts ISO YMD per `records/validation.py`)
- The two regex constants `YYYYMMDD_RE` and `MM_DD_YYYY_RE` (lines 178-179) are unchanged

- [ ] **Step 4: Run the tests — they pass**

```bash
cd chili_app && npx vitest run src/lib/ingestion/__tests__/validateIngestion.test.ts --reporter=verbose
```

Expected: all date-validator tests PASS, plus the existing tests still pass.

- [ ] **Step 5: Commit**

```bash
cd chili_app && git add src/lib/ingestion/validateIngestion.ts src/lib/ingestion/__tests__/validateIngestion.test.ts
git commit -m "$(cat <<'EOF'
fix(ingestion-ui): drop Date.parse fallback so client validator matches backend

The backend records/validation.py _coerce_value accepts only ISO YYYY-MM-DD,
compact YYYYMMDD, and MM/DD/YYYY. The client validator's Date.parse
fallback was accepting locale-dependent strings (e.g. "Jan 1", "2024")
the server would later reject. Tighten the client to match the server's
accepted set exactly.
EOF
)"
```

---

## Task 2: Remove hardcoded `Medicare FFS`/`Medicaid` filter from `DashboardPage`

**Files:**
- Modify: `chili_app/src/pages/DashboardPage.tsx:28-32,36-37,73`

- [ ] **Step 1: Apply the YAGNI removal**

In `chili_app/src/pages/DashboardPage.tsx`:

1. Delete lines 28-32 (the `dashboardFilters` constant).
2. Delete line 36 (the `useState` declaration for `activeFilterId`):
   ```typescript
   const [activeFilterId, setActiveFilterId] = useState('all')
   ```
3. Delete the `<FilterBar>` element on line 73 inside `<div className="page-toolbar">`. The toolbar becomes just the `<Tabs>` element.
4. Remove the `FilterBar` import on line 13 (`import { FilterBar } from '../components/ui/FilterBar'`).
5. If `useState` is no longer used after removing `activeFilterId` (check the remaining `useState('overview')` for `activeTabId` — it's still used), keep the `useState` import.

The diff should be a net deletion (~7 lines).

- [ ] **Step 2: Run lint + tsc**

```bash
cd chili_app && npm run lint
cd chili_app && npx tsc -b --pretty 2>&1 | tail -10
```

Expected: no errors. The strict TypeScript config catches any dangling reference to `activeFilterId`/`setActiveFilterId` if you missed one.

- [ ] **Step 3: Run unit tests + a focused e2e**

```bash
cd chili_app && npm run test:run
cd chili_app && npx playwright test smoke.spec.ts --reporter=line
```

Expected: smoke e2e passes — the dashboard still renders. The smoke spec is the broadest sanity check.

- [ ] **Step 4: Verify no Medicare/Medicaid strings remain**

```bash
grep -rn "Medicare\|Medicaid" chili_app/src/
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
cd chili_app && git add src/pages/DashboardPage.tsx
git commit -m "$(cat <<'EOF'
fix(frontend): remove hardcoded Medicare/Medicaid filter from dashboard

The filter labels violated the domain-reconfigurability contract and
the filter never filtered anything (activeFilterId was set but never
applied to any query). Removing instead of wiring (YAGNI).
EOF
)"
```

---

## Task 3: Remove inert global search input and scaffold eyebrow from `TopBar`

**Files:**
- Modify: `chili_app/src/components/layout/TopBar.tsx:27,31-35,1`

- [ ] **Step 1: Remove the inert search input + scaffold eyebrow**

In `chili_app/src/components/layout/TopBar.tsx`:

1. Delete line 27: `<div className="app-topbar__eyebrow">Production UI foundation</div>` (this is leftover scaffold text — the `<h1>` immediately below shows the active domain's display name).
2. Delete lines 31-35 (the entire `<label className="app-topbar__search">...</label>` block).
3. Remove `Search` from the `lucide-react` import on line 1 since it's no longer used:
   ```typescript
   import { PanelRightOpen } from 'lucide-react'
   ```

The diff should be a net deletion (~7 lines).

- [ ] **Step 2: Run lint + tsc**

```bash
cd chili_app && npm run lint
cd chili_app && npx tsc -b --pretty 2>&1 | tail -10
```

Expected: no errors. The `noUnusedLocals` rule will fail if you forgot to remove the `Search` import.

- [ ] **Step 3: Run topbar-relevant e2e**

```bash
cd chili_app && npx playwright test authenticated-shell.spec.ts --reporter=line
```

Expected: passes. If the spec asserts on the eyebrow text or the search input being present, update those assertions to match the new layout — but only if the test is making a structural assertion; do NOT add new test scaffolding for absence.

- [ ] **Step 4: Commit**

```bash
cd chili_app && git add src/components/layout/TopBar.tsx
git commit -m "$(cat <<'EOF'
fix(frontend): remove inert global search and scaffold eyebrow from TopBar

The search input had no onChange/state/query — users would type and get
nothing. The eyebrow text "Production UI foundation" was leftover
scaffolding. Both removed under YAGNI; the topbar now shows just the
domain name + role selector + realtime badge + AI panel toggle.
EOF
)"
```

---

## Task 4: Migrate `AlertTable` and related components from `types/api.ts::Alert` to `api/contracts.ts::AlertListItem`

**Files:**
- Modify: `chili_app/src/components/alerts/AlertTable.tsx:3`
- Modify: `chili_app/src/components/alerts/AlertFilters.tsx` (if it imports `Alert`/`AlertSeverity` from `types/api.ts`)
- Modify: `chili_app/src/components/alerts/__tests__/AlertTable.test.tsx` (type-only updates)

- [ ] **Step 1: Inventory consumers of the alert types from `types/api.ts`**

```bash
grep -rn "from '.*types/api'" chili_app/src/components/alerts/ chili_app/src/pages/ chili_app/src/hooks/ 2>/dev/null
```

Expected: at minimum `components/alerts/AlertTable.tsx:3`. If `AlertFilters.tsx`, `AlertDetail` (if exists), or page-level files also import `Alert`/`AlertSeverity`/`AlertStatus` from `types/api.ts`, include them in Step 2.

- [ ] **Step 2: Update imports in alert components**

In each file from Step 1, change:

```typescript
import type { Alert } from '../../types/api'
// or:
import type { Alert, AlertSeverity, AlertStatus, AlertListResponse } from '../../types/api'
```

to:

```typescript
import type { AlertListItem as Alert } from '../../api/contracts'
// or with the other types:
import type { AlertListItem as Alert, AlertSeverity, AlertStatus, AlertListResponse } from '../../api/contracts'
```

**Why the alias?** Using `import type { AlertListItem as Alert }` keeps the rest of `AlertTable.tsx` (which uses the local name `Alert` extensively) unchanged. This is a 1-line change per file, not a sweeping rename.

**Note on field shapes:** `types/api.ts::Alert` has fields the new `AlertListItem` may not have (e.g. `acknowledged`, `kb_id`, `message`). Confirm by reading both type definitions side by side and noting any access of those fields in `AlertTable.tsx` — if found, either (a) add the field to `AlertListItem` in `api/contracts.ts` (preferred if the backend actually returns it), or (b) remove the access in `AlertTable.tsx` (if the field was never populated). Do this audit BEFORE running tsc; otherwise tsc will fail loudly and you can fix per-error.

- [ ] **Step 3: Run tsc + lint**

```bash
cd chili_app && npx tsc -b --pretty 2>&1 | tail -10
cd chili_app && npm run lint
```

Expected: clean. If tsc complains about missing fields on `AlertListItem`, see Step 2 note above.

- [ ] **Step 4: Run alert unit tests**

```bash
cd chili_app && npx vitest run src/components/alerts/ --reporter=verbose
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd chili_app && git add src/components/alerts/
git commit -m "$(cat <<'EOF'
refactor(alerts): components consume Alert type from api/contracts

AlertTable, AlertFilters, and their tests now alias AlertListItem from
api/contracts as the local Alert name, removing the dependency on the
duplicate definition in src/types/api.ts. Sets up the deletion of the
duplicate useAlerts hook in the next commit.
EOF
)"
```

---

## Task 5: Delete `chili_app/src/hooks/useAlerts.ts` and the alert-specific exports from `types/api.ts`

**Files:**
- Delete: `chili_app/src/hooks/useAlerts.ts`
- Modify: `chili_app/src/types/api.ts` — remove `Alert`, `AlertListResponse`, `AlertSeverity`, `AlertStatus` exports

- [ ] **Step 1: Final consumer check**

```bash
grep -rln "from .*hooks/useAlerts" chili_app/src/
```

Expected: no output (Task 4 should have removed the last consumer; if AlertTable was importing the hook directly, that import is now gone).

```bash
grep -rln "import type.*\(Alert\|AlertListResponse\|AlertSeverity\|AlertStatus\).*from.*types/api" chili_app/src/
```

Expected: no output. If anything still matches, migrate it the same way Task 4 did.

- [ ] **Step 2: Delete the hook file**

```bash
cd chili_app && git rm src/hooks/useAlerts.ts
```

- [ ] **Step 3: Remove the alert exports from `types/api.ts`**

In `chili_app/src/types/api.ts`, delete lines 42-76 (the `AlertSeverity`, `AlertStatus`, `Alert`, `AlertListResponse` definitions). Leave the rest of the file (KnowledgeBase, Entity, Relationship, EvidencePack, TimelineEvent types) intact — those are still consumed by other hooks/components and migrating them is out of scope.

- [ ] **Step 4: Run the full type check + lint + tests**

```bash
cd chili_app && npx tsc -b --pretty 2>&1 | tail -10
cd chili_app && npm run lint
cd chili_app && npm run test:run
```

Expected: all clean.

- [ ] **Step 5: Run all e2e tests**

```bash
cd chili_app && npx playwright test --reporter=line 2>&1 | tail -20
```

Expected: all pass. If `alert-acknowledge.spec.ts` or `alert-feed.spec.ts` fails, the failure will point at a hook-level assertion that's now stale; update it to use the consolidated hook from `api/alerts.ts`.

- [ ] **Step 6: Commit**

```bash
cd chili_app && git add src/types/api.ts src/hooks/useAlerts.ts
git commit -m "$(cat <<'EOF'
refactor(alerts): delete duplicate useAlerts hook and alert type exports

src/hooks/useAlerts.ts is removed; src/api/alerts.ts is now the single
source of truth for alert queries. Alert-specific types are removed from
src/types/api.ts (they're consolidated in src/api/contracts.ts as
AlertListItem + friends). Non-alert types in src/types/api.ts (KB,
Entity, EvidencePack, TimelineEvent) remain — their migration is out of
scope for this theme.
EOF
)"
```

---

## Task 6: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm acceptance criteria via grep**

```bash
grep -rn "Medicare\|Medicaid" chili_app/src/
```

Expected: no output.

```bash
grep -rn "from .*hooks/useAlerts" chili_app/src/
```

Expected: no output.

```bash
ls chili_app/src/hooks/useAlerts.ts 2>&1
```

Expected: `No such file or directory`.

```bash
grep -n "Date.parse" chili_app/src/lib/ingestion/validateIngestion.ts
```

Expected: no output.

- [ ] **Step 2: Full quality gate**

```bash
cd chili_app && npm run lint
cd chili_app && npm run test:run
cd chili_app && npm run build
```

Expected: all three clean.

- [ ] **Step 3: Full e2e suite**

```bash
cd chili_app && npx playwright test --reporter=list 2>&1 | tail -20
```

Expected: all specs pass.

- [ ] **Step 4: Manual visual smoke (the human runs this; document it)**

```bash
cd chili_app && npm run dev
# In a browser at http://localhost:5173:
# 1. Log in
# 2. Confirm Dashboard page loads with no filter bar above the KPI cards
# 3. Confirm TopBar has no global search input and no "Production UI foundation" eyebrow
# 4. Navigate to Alerts page — confirm alert list renders normally
# 5. Navigate to an Ingestion wizard, upload a record file with an invalid date
#    (e.g. "Jan 1") — confirm the client validator rejects it before submit
```

- [ ] **Step 5: No commit (verification only)**

The theme's changes are committed across the 5 prior tasks.

---

## Acceptance Criteria — Sign-off Checklist

- [ ] `isValidDateValue('2024')`, `isValidDateValue('Jan 1')`, `isValidDateValue('2024-01-15T10:00:00Z')` all return `false`; `isValidDateValue('2024-01-15')`, `isValidDateValue('20240115')`, `isValidDateValue('1/5/2024')` all return `true` (verified by tests in Task 1).
- [ ] No `Medicare` or `Medicaid` string anywhere in `chili_app/src/`.
- [ ] `TopBar` has no `<input>` element and no "Production UI foundation" text.
- [ ] `src/hooks/useAlerts.ts` does not exist.
- [ ] `src/types/api.ts` no longer exports `Alert`, `AlertListResponse`, `AlertSeverity`, or `AlertStatus`.
- [ ] `npm run lint`, `npm run test:run`, `npm run build` all green.
- [ ] All Playwright specs in `chili_app/e2e/` pass.

## Scope Discipline

- **Do NOT** delete `src/types/api.ts` wholesale. It still defines `KnowledgeBase`, `KnowledgeBaseListResponse`, `DocumentSummary`, `Entity`, `Relationship`, `EvidencePack`, `TimelineEvent`, and others consumed by 9+ hook/component files. Migrating those is out of scope for Theme 3 — file a follow-up if needed.
- **Do NOT** wire the global search input to investigation routing. The spec presents two options (YAGNI-remove vs wire it up); the YAGNI path is chosen here. If the team later wants a global search, that's a feature, not a fix.
- **Do NOT** add a `DomainConfig.ui.dashboard.filters` schema field for the dashboard filter. Theme 2 owns `DomainConfig` schema changes; if a future config-driven dashboard filter is wanted, file it as a Theme 2 follow-up.
- **Do NOT** refactor `AlertTable`'s sort/severity logic. Type migration only.
