# Sprint 1 Ingestion To Investigation Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ingestion Studio a complete demo path: submit data, understand run state, and move into Investigation with the selected knowledge base preserved.

**Architecture:** Keep this sprint frontend-only unless tests prove a backend gap. Add a small "next actions" surface in `KnowledgeBaseManagerPage`, preserve selected KB through `?kb=<id>`, and centralize analyst-facing run-state copy in `RunTimeline`.

**Tech Stack:** React 19, React Router, TanStack Query, Vite, Vitest, Testing Library.

**Spec:** [docs/superpowers/specs/2026-06-14-demoable-workflow-increments-design.md](../specs/2026-06-14-demoable-workflow-increments-design.md)

---

## File Structure

- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` — add navigation helpers and next-action panel.
- Modify: `chili_app/src/components/ingestion/RunTimeline.tsx` — render plain-language workflow and receipt states.
- Modify: `chili_app/src/components/ingestion/ingestion.css` or `chili_app/src/pages/pages.css` — add minimal next-action layout styles.
- Modify: `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx` — cover next actions and KB-preserving navigation.
- Modify: `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx` — verify incoming `kb` query param selects the matching KB.
- Modify: `chili_app/src/components/ingestion/__tests__/RunTimeline.test.tsx` — cover status labels/descriptions.
- Review: `chili_app/src/app/router.tsx` — no change expected; existing `/investigation` route should accept query params.

## Task 1: Lock The KB-Preserving Handoff With Tests

**Files:**
- Modify: `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`
- Modify: `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

- [ ] **Step 1: Wrap KnowledgeBaseManagerPage tests with a router**

If tests do not already render inside a router, wrap the page with `MemoryRouter` because the implementation will use `useNavigate`.

```tsx
import { MemoryRouter } from 'react-router-dom'

function renderKnowledgeBaseManager() {
  return render(
    <MemoryRouter>
      <KnowledgeBaseManagerPage />
    </MemoryRouter>,
  )
}
```

- [ ] **Step 2: Add the failing post-submit next-actions test**

```tsx
it('shows next actions after document submission', async () => {
  renderKnowledgeBaseManager()

  await screen.findByText('Ingestion Studio')
  await userEvent.click(screen.getByRole('button', { name: /documents/i }))
  await userEvent.upload(
    screen.getByLabelText(/document files/i),
    new File(['policy'], 'policy.txt', { type: 'text/plain' }),
  )
  await userEvent.click(screen.getByRole('button', { name: /submit documents/i }))

  expect(await screen.findByText(/1 document accepted/i)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /watch runs/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /investigate entities/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /review alerts/i })).toBeInTheDocument()
})
```

- [ ] **Step 3: Add the failing KB-preserving navigation test**

Mock `useNavigate` in the test file and assert the exact route object.

```tsx
expect(navigateMock).toHaveBeenCalledWith({
  pathname: '/investigation',
  search: 'kb=kb-1',
})
```

- [ ] **Step 4: Add the failing Investigation Workbench selection test**

```tsx
render(
  <MemoryRouter initialEntries={['/investigation?kb=kb-claims']}>
    <InvestigationWorkbenchPage />
  </MemoryRouter>,
)

expect(screen.getByLabelText('Knowledge base')).toHaveValue('kb-claims')
```

- [ ] **Step 5: Verify the new tests fail**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx
```

Expected: the newly added next-action and navigation assertions fail before implementation.

## Task 2: Add Ingestion Next Actions

**Files:**
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx`
- Modify: `chili_app/src/components/ingestion/ingestion.css` or `chili_app/src/pages/pages.css`

- [ ] **Step 1: Import and initialize navigation**

```tsx
import { useNavigate } from 'react-router-dom'

const navigate = useNavigate()
```

- [ ] **Step 2: Add KB-aware navigation helpers inside `KnowledgeBaseManagerPage`**

```tsx
function kbSearch() {
  const params = new URLSearchParams()
  if (activeKnowledgeBaseId) {
    params.set('kb', activeKnowledgeBaseId)
  }
  return params.toString()
}

function navigateWithKb(pathname: string) {
  navigate({ pathname, search: kbSearch() })
}
```

- [ ] **Step 3: Render `NextActionsPanel` in the right-side context column**

Place it after `SelectedKnowledgeBaseSummary` and before `RunTimeline`.

```tsx
<Card>
  <NextActionsPanel
    disabled={!activeKnowledgeBaseId}
    hasReceipts={studio.receipts.length > 0}
    hasWorkflows={(workflowsQuery.data?.items ?? []).length > 0}
    onWatchRuns={() => studio.setCurrentStep('runs')}
    onInvestigate={() => navigateWithKb('/investigation')}
    onReviewAlerts={() => navigateWithKb('/alerts')}
  />
</Card>
```

- [ ] **Step 4: Implement `NextActionsPanel` in `KnowledgeBaseManagerPage.tsx`**

```tsx
function NextActionsPanel({
  disabled,
  hasReceipts,
  hasWorkflows,
  onWatchRuns,
  onInvestigate,
  onReviewAlerts,
}: {
  disabled: boolean
  hasReceipts: boolean
  hasWorkflows: boolean
  onWatchRuns: () => void
  onInvestigate: () => void
  onReviewAlerts: () => void
}) {
  const activityLabel = hasWorkflows
    ? 'Runs are updating for this knowledge base.'
    : hasReceipts
      ? 'Submission accepted. Watch for queued or running workflow updates.'
      : 'Submit documents or records to unlock the handoff path.'

  return (
    <section className="ingestion-next-actions" aria-labelledby="ingestion-next-actions-title">
      <strong id="ingestion-next-actions-title">Next actions</strong>
      <p className="page-copy-block">{activityLabel}</p>
      <div className="ingestion-next-actions__buttons">
        <button className="page-button page-button--secondary" disabled={disabled} onClick={onWatchRuns} type="button">
          Watch runs
        </button>
        <button className="page-button" disabled={disabled} onClick={onInvestigate} type="button">
          Investigate entities
        </button>
        <button className="page-button page-button--secondary" disabled={disabled} onClick={onReviewAlerts} type="button">
          Review alerts
        </button>
      </div>
    </section>
  )
}
```

- [ ] **Step 5: Add layout CSS**

```css
.ingestion-next-actions {
  display: grid;
  gap: 0.75rem;
}

.ingestion-next-actions__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
```

- [ ] **Step 6: Run the focused tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx
```

Expected: Knowledge Base Manager next-action tests pass.

## Task 3: Add Plain-Language Run State

**Files:**
- Modify: `chili_app/src/components/ingestion/RunTimeline.tsx`
- Modify: `chili_app/src/components/ingestion/__tests__/RunTimeline.test.tsx`

- [ ] **Step 1: Add failing workflow-state tests**

```tsx
it.each([
  ['queued', 'Queued', 'The run is waiting for a worker.'],
  ['running', 'Running', 'The backend is processing this run.'],
  ['completed', 'Completed', 'Investigation data is ready to review.'],
  ['failed', 'Failed', 'Review the error and retry when fixed.'],
  ['cancelled', 'Cancelled', 'The run was stopped before completion.'],
] as const)('renders plain-language %s workflow state', (status, label, description) => {
  render(<RunTimeline workflows={[{ ...workflows[0], status }]} receipts={[]} />)

  expect(screen.getByText(label)).toBeInTheDocument()
  expect(screen.getByText(description)).toBeInTheDocument()
})
```

- [ ] **Step 2: Add a failing accepted-receipt copy test**

```tsx
render(<RunTimeline workflows={[]} receipts={receipts} />)

expect(screen.getByText('Accepted')).toBeInTheDocument()
expect(screen.getByText('Submission accepted. Watch for queued or running workflow updates.')).toBeInTheDocument()
```

- [ ] **Step 3: Implement status copy helpers**

```tsx
const workflowStatusCopy = {
  queued: { label: 'Queued', description: 'The run is waiting for a worker.' },
  running: { label: 'Running', description: 'The backend is processing this run.' },
  completed: { label: 'Completed', description: 'Investigation data is ready to review.' },
  failed: { label: 'Failed', description: 'Review the error and retry when fixed.' },
  cancelled: { label: 'Cancelled', description: 'The run was stopped before completion.' },
} satisfies Record<WorkflowRunResponse['status'], { label: string; description: string }>

const receiptStatusCopy = {
  accepted: { label: 'Accepted', description: 'Submission accepted. Watch for queued or running workflow updates.' },
  failed: { label: 'Failed', description: 'Submission failed before a run could start.' },
} satisfies Record<IngestionReceiptEntry['status'], { label: string; description: string }>
```

- [ ] **Step 4: Render copy without changing cancellation behavior**

Use the copy label in the `Chip`, render the description near each timeline message, and keep cancel available only for `queued` and `running`.

- [ ] **Step 5: Run timeline tests**

Run:

```bash
cd chili_app
npm run test:run -- src/components/ingestion/__tests__/RunTimeline.test.tsx
```

Expected: all timeline tests pass.

## Task 4: Final Sprint Verification

**Files:**
- Review: `chili_app/src/app/router.tsx`

- [ ] **Step 1: Confirm no route change is needed**

Verify existing route `{ path: 'investigation' }` handles `/investigation?kb=kb-1`. Add no new route unless a test fails because of routing.

- [ ] **Step 2: Run focused frontend tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/components/ingestion/__tests__/RunTimeline.test.tsx
```

Expected: all pass.

- [ ] **Step 3: Run build and lint**

Run:

```bash
cd chili_app
npm run build
npm run lint
```

Expected: build and lint complete without new errors.

## Acceptance Checks

- [ ] After a document upload, Ingestion Studio shows `Next actions`.
- [ ] `Watch runs` leaves the analyst in Ingestion Studio and moves the wizard state to `runs`.
- [ ] `Investigate entities` navigates to `/investigation?kb=<selected-kb>`.
- [ ] Investigation Workbench selects the KB from the query string.
- [ ] Run timeline displays `Accepted`, `Queued`, `Running`, `Completed`, `Failed`, and `Cancelled`.
- [ ] Failed workflow errors remain visible with `role="alert"`.

## Demo Script

1. Open `/knowledge-bases`.
2. Select or create a knowledge base.
3. Upload one document or submit one valid record.
4. Confirm the timeline says `Accepted` and shows next actions.
5. Click `Investigate entities`.
6. Confirm the browser lands on `/investigation?kb=<selected-kb>`.
7. Confirm the Investigation Workbench KB selector shows the same knowledge base.
