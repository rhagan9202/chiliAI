# SAFE-CMS-019 Enterprise Visual Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give core CMS analyst pages a reusable operational status language, tighter enterprise-density guardrails, and accessible controls without redesigning the app shell.

**Architecture:** Extend the existing `components/ui` layer with a semantic `StatusPill` primitive instead of adding a UI framework. Refactor Dashboard, Alert Feed, and Case Management status indicators to use that primitive, then harden shared CSS/token rules so future pages stay within the same visual language.

**Tech Stack:** React 19, TypeScript, Vite 8, Vitest, Testing Library, CSS Modules/global CSS, lucide-react.

---

## File Structure

- Create `chili_app/src/components/ui/StatusPill.tsx`: shared operational status badge with icon, tone, label, optional accessible context, and compact display.
- Create `chili_app/src/components/ui/statusPill.ts`: status/priority/severity tone helpers reused by pages and tests.
- Create `chili_app/src/components/ui/__tests__/StatusPill.test.tsx`: primitive accessibility and label tests.
- Modify `chili_app/src/components/ui/ui.css`: status pill styles and card/control density adjustments.
- Modify `chili_app/src/theme/tokens.ts`: card radii tokens no larger than 8px.
- Modify `chili_app/src/theme/__tests__/contrast.test.ts`: guard status-pill tone readability and radius limits.
- Modify `chili_app/src/pages/DashboardPage.tsx`: workflow state and queue counts use semantic status pills.
- Modify `chili_app/src/pages/AlertFeedPage.tsx`: alert severity/status/SLA/freshness metadata use status pills.
- Modify `chili_app/src/pages/CaseManagementPage.tsx`: case queue and case detail metadata use status pills.
- Modify focused page tests under `chili_app/src/pages/__tests__/`: assert semantic badges and accessible labels.
- Modify `chili_app/README.md` and `docs/architecture.md`: document the reusable operational badge/status convention.

## Implementation Status

- Completed in this pass: none.
- Remaining work: Tasks 1 through 5.

---

### Task 1: Shared Operational Status Primitive

**Files:**
- Create: `chili_app/src/components/ui/StatusPill.tsx`
- Create: `chili_app/src/components/ui/statusPill.ts`
- Modify: `chili_app/src/components/ui/ui.css`
- Test: `chili_app/src/components/ui/__tests__/StatusPill.test.tsx`

- [x] **Step 1: Write failing primitive tests**

Create `StatusPill` tests that assert:

```tsx
render(<StatusPill label="Running" tone="warning" context="Workflow state" />)
expect(screen.getByText('Running')).toBeInTheDocument()
expect(screen.getByLabelText('Workflow state: Running')).toBeInTheDocument()
expect(screen.getByTestId('status-pill-icon')).toHaveAttribute('aria-hidden', 'true')
```

Also assert `statusToneForValue('failed') === 'danger'`, `statusToneForValue('completed') === 'success'`, `statusToneForValue('open') === 'info'`, `statusToneForValue('closed') === 'success'`, and `priorityToneForValue('critical') === 'danger'`.

- [x] **Step 2: Run focused RED**

Run:

```bash
npm run test:run -- src/components/ui/__tests__/StatusPill.test.tsx
```

Expected: FAIL because `StatusPill` and `statusPill` do not exist.

- [x] **Step 3: Implement minimal primitive**

Implement:

```tsx
type StatusPillTone = 'default' | 'info' | 'success' | 'warning' | 'danger' | 'network'

type StatusPillProps = {
  className?: string
  compact?: boolean
  context?: string
  label: string
  tone?: StatusPillTone
}
```

`StatusPill` renders a non-interactive `<span className="status-pill ...">`, includes a decorative lucide icon chosen by tone, and uses `aria-label={context ? `${context}: ${label}` : label}`. It must not use negative letter spacing or viewport-based font sizes.

`statusPill.ts` exports `STATUS_PILL_TONES`, `statusToneForValue(value: string)`, and `priorityToneForValue(value: string)`.

- [x] **Step 4: Run focused GREEN**

Run:

```bash
npm run test:run -- src/components/ui/__tests__/StatusPill.test.tsx
npm run build
```

- [x] **Step 5: Commit**

Run:

```bash
git add chili_app/src/components/ui/StatusPill.tsx chili_app/src/components/ui/statusPill.ts chili_app/src/components/ui/ui.css chili_app/src/components/ui/__tests__/StatusPill.test.tsx docs/superpowers/plans/2026-08-05-safe-cms-019-enterprise-visual-design.md
git commit -m "feat: add operational status pill"
```

### Task 2: Core Page Status Language

**Files:**
- Modify: `chili_app/src/pages/DashboardPage.tsx`
- Modify: `chili_app/src/pages/AlertFeedPage.tsx`
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Test: `chili_app/src/pages/__tests__/DashboardPage.test.tsx`
- Test: `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx`
- Test: `chili_app/src/pages/__tests__/CaseManagementPage.test.tsx`

- [ ] **Step 1: Write failing page tests**

Add assertions that:

- Dashboard exposes `Workflow state: running` or `Workflow state: idle` through a status pill accessible name.
- Alert Feed exposes per-row `Alert severity: critical`, `Alert status: open`, `Score freshness: fresh`, and `SLA state: SLA current` badge labels.
- Case Management exposes case list metadata as separate badges and case detail labels `Case status: open` and `Case priority: high`.

- [ ] **Step 2: Run focused RED**

Run:

```bash
npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx
```

Expected: FAIL because the current pages use generic chip text or plain `status · priority` text without those accessible names.

- [ ] **Step 3: Refactor status metadata to `StatusPill`**

Use:

```tsx
import { StatusPill } from '../components/ui/StatusPill'
import { priorityToneForValue, statusToneForValue } from '../components/ui/statusPill'
```

Replace generic operational `Chip` instances for workflow status, alert severity/status/freshness/SLA, and case status/priority with `StatusPill`. Keep count chips as `Chip`; they are metrics, not statuses.

- [ ] **Step 4: Run focused GREEN**

Run:

```bash
npm run test:run -- src/pages/__tests__/DashboardPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx
npm run build
```

- [ ] **Step 5: Commit**

Run:

```bash
git add chili_app/src/pages/DashboardPage.tsx chili_app/src/pages/AlertFeedPage.tsx chili_app/src/pages/CaseManagementPage.tsx chili_app/src/pages/__tests__/DashboardPage.test.tsx chili_app/src/pages/__tests__/AlertFeedPage.test.tsx chili_app/src/pages/__tests__/CaseManagementPage.test.tsx docs/superpowers/plans/2026-08-05-safe-cms-019-enterprise-visual-design.md
git commit -m "feat: unify core page status badges"
```

### Task 3: Enterprise Density And Radius Guardrails

**Files:**
- Modify: `chili_app/src/components/ui/ui.css`
- Modify: `chili_app/src/pages/pages.css`
- Modify: `chili_app/src/theme/tokens.ts`
- Modify: `chili_app/src/theme/__tests__/contrast.test.ts`

- [ ] **Step 1: Write failing visual guardrail tests**

Extend `contrast.test.ts` to assert:

```ts
expect(radii.lg).toBe('8px')
expect(radii.md).toBe('8px')
```

Also assert all `STATUS_PILL_TONES` colors meet AA normal text contrast on `s2` and `s3`.

- [ ] **Step 2: Run focused RED**

Run:

```bash
npm run test:run -- src/theme/__tests__/contrast.test.ts
```

Expected: FAIL because `radii.md` is `9px` and `radii.lg` is `12px`.

- [ ] **Step 3: Apply compact enterprise guardrails**

Change shared card and feedback-state radii to 8px or less, reduce overlarge page placeholder radius, keep buttons and fixed-format controls at stable min-heights, and ensure `.status-pill` uses stable dimensions and wrapping-safe text.

- [ ] **Step 4: Run focused GREEN**

Run:

```bash
npm run test:run -- src/theme/__tests__/contrast.test.ts
npm run build
```

- [ ] **Step 5: Commit**

Run:

```bash
git add chili_app/src/components/ui/ui.css chili_app/src/pages/pages.css chili_app/src/theme/tokens.ts chili_app/src/theme/__tests__/contrast.test.ts docs/superpowers/plans/2026-08-05-safe-cms-019-enterprise-visual-design.md
git commit -m "style: tighten enterprise visual guardrails"
```

### Task 4: Design Convention Documentation

**Files:**
- Modify: `chili_app/README.md`
- Modify: `docs/architecture.md`

- [ ] **Step 1: Write documentation update**

Document:

- `StatusPill` is for state/severity/priority/SLA/readiness.
- `Chip` remains for counts, tags, and compact labels that are not state.
- Cards and framed repeated items use 8px or smaller radii.
- New route work should prefer existing `SectionHeader`, `FilterGroup`, `Tabs`, `Card`, `Chip`, and `StatusPill` before adding page-specific styling.

- [ ] **Step 2: Verify documentation references**

Run:

```bash
rg -n "StatusPill|status pill|8px|Chip remains" chili_app/README.md docs/architecture.md
git diff --check
```

- [ ] **Step 3: Commit**

Run:

```bash
git add chili_app/README.md docs/architecture.md docs/superpowers/plans/2026-08-05-safe-cms-019-enterprise-visual-design.md
git commit -m "docs: document enterprise visual primitives"
```

### Task 5: Final Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-08-05-safe-cms-019-enterprise-visual-design.md`

- [ ] **Step 1: Run frontend gates**

Run:

```bash
npm run test:run
npm run lint
npm run build
```

- [ ] **Step 2: Run backend smoke gates**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_app.py -q
uv run --project backend pyright
```

- [ ] **Step 3: Run whitespace and branch checks**

Run:

```bash
git diff --check
git status --short --branch
```

- [ ] **Step 4: Commit final plan status**

Run:

```bash
git add docs/superpowers/plans/2026-08-05-safe-cms-019-enterprise-visual-design.md
git commit -m "docs: update safe cms 019 plan status"
```
