# Ingestion Studio Prerequisite vs. Validation Error Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Ingestion Studio's Validate stepper item and ValidationPanel from rendering required-state issues (no KB selected, no source type picked, no records feed picked) as red errors on cold load. Instead, surface them as info-toned "prerequisites" while keeping real content validation failures looking like errors.

**Architecture:** Add an optional `kind: 'prerequisite' | 'content'` discriminator on `ValidationIssue`. `validateRequiredWizardState` tags its output as `'prerequisite'`; all other validators leave `kind` absent (treated as `'content'`). The page's stepper-state computation filters by `kind` so only content-error issues trip the Validate step. `ValidationPanel` partitions incoming issues and renders prerequisites in a separate info-toned section above the existing source-grouped sections.

**Tech Stack:** React 19, TypeScript strict, Vitest + Testing Library, Tanstack Query, Zustand store (`useIngestionStudioStore`).

**Spec:** `docs/superpowers/specs/2026-05-21-ingestion-prerequisite-vs-error-design.md`

---

## Conventions Used Throughout

- All paths are relative to repo root unless prefixed with `/`.
- Commands run from `chili_app/` unless stated otherwise.
- `tsc -b --noEmit` and `npm run lint` must remain clean at every commit boundary.
- Tests use Vitest + `@testing-library/react` + `@testing-library/user-event`.
- `ValidationIssue` typing change is additive (optional field), so existing call sites compile without modification. Consumers that care about the kind use `(issue.kind ?? 'content')`.

---

## Task 1: Add `ValidationKind` discriminator on `ValidationIssue`

**Files:**
- Modify: `chili_app/src/lib/ingestion/types.ts`

- [ ] **Step 1: Add the type field**

Replace the existing `ValidationIssue` definition in `chili_app/src/lib/ingestion/types.ts` (currently lines 16-23) with:

```ts
export type ValidationKind = 'prerequisite' | 'content'

export type ValidationIssue = {
  id: string
  source: ValidationSource
  severity: ValidationSeverity
  kind?: ValidationKind
  message: string
  rowIndex?: number
  field?: string
}
```

Keep the existing `ValidationSeverity` and `ValidationSource` types above the `ValidationIssue` definition unchanged.

- [ ] **Step 2: Verify typecheck still clean**

Run: `cd chili_app && npx tsc -b --noEmit`

Expected: no output. The change is additive (new optional field), so no existing call site breaks.

- [ ] **Step 3: Commit**

```bash
git add chili_app/src/lib/ingestion/types.ts
git commit -m "feat(ingestion-types): add optional kind discriminator to ValidationIssue"
```

---

## Task 2: Tag prerequisite issues at the producer

**Files:**
- Modify: `chili_app/src/lib/ingestion/validateIngestion.ts`
- Modify: `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`

- [ ] **Step 1: Update the producer**

In `chili_app/src/lib/ingestion/validateIngestion.ts`, the current `validateRequiredWizardState` function (lines 16-40) emits three issues using the shared `issue()` helper which does not set `kind`. Modify the function so all three issues carry `kind: 'prerequisite'`. Replace the function with:

```ts
export function validateRequiredWizardState({
  knowledgeBaseId,
  sourceType,
  feedName,
}: {
  knowledgeBaseId: string | null
  sourceType: IngestionSourceType | null
  feedName: string | null
}): ValidationIssue[] {
  const issues: ValidationIssue[] = []

  if (!knowledgeBaseId) {
    issues.push({
      ...issue('missing-kb', 'Select a knowledge base before submitting.'),
      kind: 'prerequisite',
    })
  }

  if (!sourceType) {
    issues.push({
      ...issue('missing-source', 'Choose Documents or Structured Records before submitting.'),
      kind: 'prerequisite',
    })
  }

  if (sourceType === 'records' && !feedName) {
    issues.push({
      ...issue('missing-feed', 'Select a structured records feed before submitting.'),
      kind: 'prerequisite',
    })
  }

  return issues
}
```

Leave every other validator in the file (`validateDocumentFiles`, `validateRecordFile`, `validateRecordRows`, `validatePrimitive`, helpers) unchanged. They continue to NOT set `kind`, which consumers treat as `'content'`.

- [ ] **Step 2: Add test assertions for the new field**

In `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`, update the first test (`'requires selected knowledge base and source type'`, currently lines 43-54) so that it asserts both the message list AND the `kind` field. Replace its body with:

```ts
  it('requires selected knowledge base and source type', () => {
    const issues = validateRequiredWizardState({
      knowledgeBaseId: null,
      sourceType: null,
      feedName: null,
    })

    expect(issues.map((issue) => issue.message)).toEqual([
      'Select a knowledge base before submitting.',
      'Choose Documents or Structured Records before submitting.',
    ])
    expect(issues.every((issue) => issue.kind === 'prerequisite')).toBe(true)
  })
```

Update the second test (`'requires feed name only for structured records'`, currently lines 56-72) so that its `missing-feed` assertion also covers the `kind`. Replace the records-branch expectation with:

```ts
    expect(
      validateRequiredWizardState({
        knowledgeBaseId: 'kb-1',
        sourceType: 'records',
        feedName: null,
      }),
    ).toMatchObject([{ id: 'missing-feed', severity: 'error', source: 'client', kind: 'prerequisite' }])
```

Then append a new test inside the existing `describe('ingestion validation', ...)` block, immediately after the `'requires feed name only for structured records'` test:

```ts
  it('does not tag content-level validation issues with a prerequisite kind', () => {
    const fileIssues = validateDocumentFiles([], validationConfig)
    const recordIssues = validateRecordRows(feed, [])

    expect(fileIssues.every((issue) => issue.kind === undefined)).toBe(true)
    expect(recordIssues.every((issue) => issue.kind === undefined)).toBe(true)
  })
```

- [ ] **Step 3: Run the validator tests**

Run: `cd chili_app && npm run test:run -- src/lib/ingestion/__tests__/validateIngestion.test.ts`

Expected: all tests pass (the file currently has ~12 tests; expect 13 after the new one is added).

- [ ] **Step 4: Commit**

```bash
git add chili_app/src/lib/ingestion/validateIngestion.ts chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts
git commit -m "feat(ingestion-validate): tag required-state issues with prerequisite kind"
```

---

## Task 3: Update the page's stepper logic

**Files:**
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`
- Modify: `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`

- [ ] **Step 1: Update the test file imports**

In `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`, ensure `within` is imported from `@testing-library/react`. The current import (line 2) is:

```ts
import { render, screen, waitFor } from '@testing-library/react'
```

Replace it with:

```ts
import { render, screen, waitFor, within } from '@testing-library/react'
```

- [ ] **Step 2: Add a small helper for stepper-item lookup**

Just below the existing `parseValidRecords` helper (currently ending around line 256, before the `describe('KnowledgeBaseManagerPage Ingestion Studio', ...)` block), add:

```ts
function getStepperItem(stepLabel: string): HTMLLIElement {
  const item = screen
    .getAllByRole('listitem')
    .find((li) => within(li).queryByText(stepLabel))
  if (!item) {
    throw new Error(`Stepper item with label "${stepLabel}" not found`)
  }
  return item as HTMLLIElement
}
```

- [ ] **Step 3: Add the failing stepper-behaviour tests**

Inside the existing `describe('KnowledgeBaseManagerPage Ingestion Studio', ...)` block (which has `installFetchMock()` and store reset in its `beforeEach` already — see lines 261-263), append these three new tests at the end of the block, just before the closing `})`:

```ts
  it('renders the Validate stepper item as idle on cold load (no error chip, no complete chip)', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')

    const validateItem = getStepperItem('Validate')
    expect(within(validateItem).queryByText('Needs attention')).not.toBeInTheDocument()
    expect(within(validateItem).queryByText('Complete')).not.toBeInTheDocument()
  })

  it('flips Validate to Needs attention when an empty document file is queued', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File([''], 'empty.txt', { type: 'text/plain' }),
    )

    const validateItem = getStepperItem('Validate')
    expect(within(validateItem).getByText('Needs attention')).toBeInTheDocument()
  })

  it('marks Validate as Complete when a clean document file is queued', async () => {
    renderWithClient(<KnowledgeBaseManagerPage />)

    await screen.findByText('Ingestion Studio')
    await userEvent.click(screen.getByRole('radio', { name: /Documents/i }))
    await userEvent.upload(
      screen.getByLabelText('Document files'),
      new File(['hello'], 'policy.txt', { type: 'text/plain' }),
    )

    const validateItem = getStepperItem('Validate')
    expect(within(validateItem).getByText('Complete')).toBeInTheDocument()
  })
```

Notes on what each test verifies:
- **Test 1 (cold load):** the default `installFetchMock()` returns one KB (`Fraud KB`). The page auto-selects it. With no source type picked and no files, Validate must be idle (no chips). Today this test fails because `errorStepIds` flips on the prereq issue.
- **Test 2 (bad file):** queues an empty file which `validateDocumentFiles` flags as a content error. Validate must show "Needs attention".
- **Test 3 (clean file):** queues a valid file with no issues and no missing prereqs. Validate must show "Complete".

- [ ] **Step 4: Run tests to verify they fail in the expected ways**

Run: `cd chili_app && npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`

Expected: the new cold-load test fails because the current page logic flips `errorStepIds` to include `'validate'` when `currentIssues.length > 0` — which is true on cold load — so `within(validateItem).queryByText('Needs attention')` finds the chip and the assertion fails. The bad-file and clean-file tests may also fail today depending on which chip the current logic emits — that's expected; they will pass after Step 5.

- [ ] **Step 5: Update the page logic**

In `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`, replace the existing `completedStepIds`/`errorStepIds` block (currently lines 245-252) with:

```tsx
  const contentErrors = currentIssues.filter(
    (item) => (item.kind ?? 'content') === 'content' && item.severity === 'error',
  )
  const userHasSubmittableState =
    Boolean(activeKnowledgeBaseId) &&
    Boolean(studio.sourceType) &&
    (studio.pendingFiles.length > 0 || studio.parsedRows.length > 0)

  const completedStepIds = new Set([
    ...(activeKnowledgeBaseId ? (['knowledge-base'] as const) : []),
    ...(studio.sourceType ? (['source'] as const) : []),
    ...(studio.pendingFiles.length > 0 || studio.parsedRows.length > 0 ? (['preview'] as const) : []),
    ...(userHasSubmittableState && contentErrors.length === 0 ? (['validate'] as const) : []),
    ...(studio.receipts.length > 0 ? (['submit'] as const) : []),
  ])
  const errorStepIds = new Set(contentErrors.length > 0 ? (['validate'] as const) : [])
```

The rest of the function (the return statement and downstream JSX) is unchanged. `currentIssues` still flows into `<ValidationPanel issues={currentIssues} />` as before.

- [ ] **Step 6: Run page tests to verify they pass**

Run: `cd chili_app && npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`

Expected: all tests in the file pass, including the three new stepper-behaviour tests.

- [ ] **Step 7: Commit**

```bash
git add chili_app/src/pages/KnowledgeBaseManagerPage.tsx chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx
git commit -m "fix(ingestion-studio): stop tripping Validate step for prereq-only issues"
```

---

## Task 4: ValidationPanel partitions and renders Prerequisites section

**Files:**
- Modify: `chili_app/src/components/ingestion/ValidationPanel.tsx`
- Modify: `chili_app/src/components/ingestion/ingestion.css`
- Modify: `chili_app/src/components/ingestion/__tests__/ValidationPanel.test.tsx`

- [ ] **Step 1: Add the failing panel tests**

In `chili_app/src/components/ingestion/__tests__/ValidationPanel.test.tsx`, add three new tests inside the existing `describe('ValidationPanel', ...)` block (append after the existing `'groups validation issues by source label...'` test, before the closing `})`):

```ts
  it('renders a Prerequisites section with info tone when only prerequisite issues are present', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'missing-kb',
        source: 'client',
        severity: 'error',
        kind: 'prerequisite',
        message: 'Select a knowledge base before submitting.',
      },
      {
        id: 'missing-source',
        source: 'client',
        severity: 'error',
        kind: 'prerequisite',
        message: 'Choose Documents or Structured Records before submitting.',
      },
    ]

    render(<ValidationPanel issues={issues} />)

    const prereq = screen.getByRole('region', { name: /prerequisites/i })
    expect(within(prereq).getByText('2 to do')).toBeInTheDocument()
    expect(within(prereq).getByText('Select a knowledge base before submitting.')).toBeInTheDocument()
    expect(within(prereq).getByText('Choose Documents or Structured Records before submitting.')).toBeInTheDocument()

    // The "Ready for submission" empty state must NOT appear when prerequisites are present.
    expect(screen.queryByText('Ready for submission')).not.toBeInTheDocument()

    // No source-grouped Client check / Backend response section appears when no content issues exist.
    expect(screen.queryByRole('region', { name: /client check/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: /backend response/i })).not.toBeInTheDocument()
  })

  it('renders both Prerequisites and Client check sections when both kinds are present', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'missing-kb',
        source: 'client',
        severity: 'error',
        kind: 'prerequisite',
        message: 'Select a knowledge base before submitting.',
      },
      {
        id: 'row-1-npi-pattern',
        source: 'client',
        severity: 'error',
        message: 'Row 1 field Provider NPI does not match ^[0-9]{10}$.',
      },
    ]

    render(<ValidationPanel issues={issues} />)

    const prereq = screen.getByRole('region', { name: /prerequisites/i })
    expect(within(prereq).getByText('1 to do')).toBeInTheDocument()

    const clientGroup = screen.getByRole('region', { name: /client check/i })
    expect(within(clientGroup).getByText('1 issue')).toBeInTheDocument()
    expect(
      within(clientGroup).getByText('Row 1 field Provider NPI does not match ^[0-9]{10}$.'),
    ).toBeInTheDocument()
  })

  it('renders only the existing source-grouped sections when there are no prerequisite issues', () => {
    const issues: ValidationIssue[] = [
      {
        id: 'row-1-npi-pattern',
        source: 'client',
        severity: 'error',
        message: 'Row 1 field Provider NPI does not match ^[0-9]{10}$.',
      },
    ]

    render(<ValidationPanel issues={issues} />)

    expect(screen.queryByRole('region', { name: /prerequisites/i })).not.toBeInTheDocument()
    const clientGroup = screen.getByRole('region', { name: /client check/i })
    expect(within(clientGroup).getByText('1 issue')).toBeInTheDocument()
  })
```

- [ ] **Step 2: Run panel tests to verify they fail**

Run: `cd chili_app && npm run test:run -- src/components/ingestion/__tests__/ValidationPanel.test.tsx`

Expected: the three new tests fail (no Prerequisites section is rendered yet; `getByRole('region', { name: /prerequisites/i })` throws).

- [ ] **Step 3: Implement the panel changes**

Replace the entire body of `chili_app/src/components/ingestion/ValidationPanel.tsx` with:

```tsx
import { Chip } from '../ui/Chip'
import { EmptyState } from '../ui/EmptyState'
import type { ValidationIssue, ValidationSource } from '../../lib/ingestion/types'
import './ingestion.css'

type ValidationPanelProps = {
  issues: ValidationIssue[]
}

const sourceLabels: Record<ValidationSource, string> = {
  client: 'Client check',
  backend: 'Backend response',
}

const sourceOrder: ValidationSource[] = ['client', 'backend']

function countLabel(count: number): string {
  return `${count} ${count === 1 ? 'issue' : 'issues'}`
}

function prerequisiteCountLabel(count: number): string {
  return `${count} to do`
}

export function ValidationPanel({ issues }: ValidationPanelProps) {
  const prerequisiteIssues = issues.filter((issue) => issue.kind === 'prerequisite')
  const contentIssues = issues.filter((issue) => (issue.kind ?? 'content') === 'content')

  if (prerequisiteIssues.length === 0 && contentIssues.length === 0) {
    return (
      <EmptyState
        title="Ready for submission"
        description="No validation issues were found."
      />
    )
  }

  return (
    <div className="ingestion-validation-panel">
      {prerequisiteIssues.length > 0 ? (
        <section
          className="ingestion-validation-panel__group"
          aria-labelledby="validation-prerequisites-title"
        >
          <div className="ingestion-validation-panel__group-header">
            <h3
              id="validation-prerequisites-title"
              className="ingestion-validation-panel__group-title"
            >
              Prerequisites
            </h3>
            <Chip tone="info" label={prerequisiteCountLabel(prerequisiteIssues.length)} />
          </div>
          <ul className="ingestion-validation-panel__list">
            {prerequisiteIssues.map((issue) => (
              <li key={issue.id} className="ingestion-validation-panel__issue">
                <span className="ingestion-validation-panel__severity ingestion-validation-panel__severity--prerequisite">
                  to do
                </span>
                <span className="ingestion-validation-panel__message">{issue.message}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {sourceOrder.map((source) => {
        const sourceIssues = contentIssues.filter((issue) => issue.source === source)

        if (sourceIssues.length === 0) {
          return null
        }

        const label = sourceLabels[source]

        return (
          <section
            key={source}
            className="ingestion-validation-panel__group"
            aria-labelledby={`validation-${source}-title`}
          >
            <div className="ingestion-validation-panel__group-header">
              <h3
                id={`validation-${source}-title`}
                className="ingestion-validation-panel__group-title"
              >
                {label}
              </h3>
              <Chip
                tone={sourceIssues.some((issue) => issue.severity === 'error') ? 'danger' : 'warning'}
                label={countLabel(sourceIssues.length)}
              />
            </div>
            <ul className="ingestion-validation-panel__list">
              {sourceIssues.map((issue) => (
                <li key={issue.id} className="ingestion-validation-panel__issue">
                  <span
                    className={[
                      'ingestion-validation-panel__severity',
                      `ingestion-validation-panel__severity--${issue.severity}`,
                    ].join(' ')}
                  >
                    {issue.severity}
                  </span>
                  <span className="ingestion-validation-panel__message">{issue.message}</span>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
```

Key behaviour:
- Partition by `kind`. Prerequisites are `kind === 'prerequisite'`; content is `kind ?? 'content' === 'content'` so untagged issues default to content.
- Render Prerequisites first if present, then the existing source-grouped sections for content only.
- When only prerequisites are present, the source-grouped sections render nothing.
- When nothing is present, the existing `EmptyState` falls through unchanged.

- [ ] **Step 4: Add CSS for the prerequisite severity label**

In `chili_app/src/components/ingestion/ingestion.css`, locate the existing severity rules (currently lines 215-225):

```css
.ingestion-validation-panel__severity--error {
  color: var(--c-red);
}

.ingestion-validation-panel__severity--warning {
  color: var(--c-amber);
}

.ingestion-validation-panel__severity--info {
  color: var(--c-cyan);
}
```

Append immediately after the `--info` rule:

```css
.ingestion-validation-panel__severity--prerequisite {
  color: var(--c-cyan);
}
```

(`--c-cyan` is the project's info colour and matches the `tone="info"` chip already used on the section header.)

- [ ] **Step 5: Run panel tests to verify they pass**

Run: `cd chili_app && npm run test:run -- src/components/ingestion/__tests__/ValidationPanel.test.tsx`

Expected: all 5 tests pass (2 existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add chili_app/src/components/ingestion/ValidationPanel.tsx chili_app/src/components/ingestion/ingestion.css chili_app/src/components/ingestion/__tests__/ValidationPanel.test.tsx
git commit -m "feat(ingestion-panel): render prerequisites in a separate info-toned section"
```

---

## Task 5: Full verification pass

The implementation is now functionally complete. Run the full gate before declaring done.

- [ ] **Step 1: Lint**

Run: `cd chili_app && npm run lint`

Expected: no errors, no warnings.

- [ ] **Step 2: TypeScript strict typecheck**

Run: `cd chili_app && npx tsc -b --noEmit`

Expected: no output.

- [ ] **Step 3: Full Vitest suite**

Run: `cd chili_app && npm run test:run`

Expected: all tests pass. Baseline before this work was 43 files / 195 tests; expect 43 files / ~202 tests (1 added in validateIngestion.test.ts + 3 added in KnowledgeBaseManagerPage.test.tsx + 3 added in ValidationPanel.test.tsx = +7 net new tests).

- [ ] **Step 4: Full Playwright e2e suite**

Run: `cd chili_app && npm run test:e2e`

Expected: 18/18 pass. No new e2e tests are required for this fix; existing e2e coverage of the KB manager page (`knowledge-base-list.spec.ts`) should remain green because the page's structure is unchanged.

- [ ] **Step 5: Manual browser smoke check**

The dev stack should already be running. Hard-reload `http://localhost:5173/knowledge-bases`.

Expected on cold load:
- IngestionStepper: Validate item shows gray `Circle` icon, no "Needs attention" chip, no "Complete" chip.
- ValidationPanel: shows a "Prerequisites" section with chip text "2 to do", listing the two prerequisite messages in cyan. No red error styling. No "Ready for submission" empty state.

Click into the existing "Fraud KB" (or create one). Stepper item for "Knowledge base" turns green/Complete; Validate stays idle. Pick a source type — Source step goes Complete, Validate still idle. Drop a known-bad file (e.g. empty file or one with unsupported content type) — Validate flips to "Needs attention". Drop a clean file — Validate flips to "Complete".

Confirm Submit Documents button is still disabled until prerequisites are satisfied (the submit-blocking logic is unchanged but worth confirming visually).

- [ ] **Step 6: No commit needed if Steps 1-5 all pass**

If any step fails, report it precisely — do not silently fix.

---

## Out of Scope (Tracked, Not Implemented)

- Click-through navigation on the stepper (items remain display-only).
- Resetting the Zustand ingestion store on route entry.
- Delete-KB confirmation dialog.
- Source-type card CSS truncation.

## Success Criteria (from spec)

- Validate step renders idle on cold load (no error or complete chip).
- ValidationPanel renders a "Prerequisites" section with info-toned `Chip` listing the two prereq messages on cold load.
- After picking a KB and source type with no content uploaded, Validate stays idle.
- After uploading a known-bad file, Validate flips to "Needs attention".
- After uploading a clean file, Validate flips to "Complete".
- Submit Documents / Submit Records continue to block submission while any prerequisite is unsatisfied (existing submit-attempt tests in `KnowledgeBaseManagerPage.test.tsx` should continue to pass without modification — that's the verification).
- Vitest, ESLint, `tsc -b`, Playwright all green.
