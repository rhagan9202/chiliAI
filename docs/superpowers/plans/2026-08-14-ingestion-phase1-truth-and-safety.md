# Ingestion Phase 1 — Truth & Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing `/knowledge-bases` page tell the truth and stop destroying user work — without moving any furniture (IA split is Phase 2).

**Architecture:** Add a shared status/timestamp primitive and `:disabled` styling; guard destructive actions with confirmation dialogs; fix file staging to append/remove/reset; scope the ingestion draft store by knowledge-base id; attach record-ingest receipts to their workflow run so the Runs timeline hydrates from the server; render the durable per-document lifecycle (`current_status`, `last_error`, drop counts) in the inventory.

**Tech Stack:** React 19 + TypeScript (Vite 8), zustand, TanStack Query, Vitest, Playwright; FastAPI + Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-08-14-ingestion-experience-redesign-design.md` (§3b, §3c, §4.3, §5 draft-store row, §6, §8 phase 1)

## Global Constraints

- Backend: `pyright` (bare, from `backend/`) must stay clean; pytest coverage ≥ 85%; run tests as `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest` (NEVER the dev `chili` DB).
- `ruff` must run with `--no-cache` in this sandbox: `backend/.venv/bin/ruff check --no-cache .`
- Frontend: TypeScript strict; `npm run lint` clean; `npm run test:run` green.
- After ANY frontend-consumed Pydantic model change: `PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json` (repo root) then `cd chili_app && npm run codegen:api`. Never hand-edit `chili_app/src/lib/api/schema.ts`.
- Frontend wire DTOs import from `chili_app/src/api/contracts.ts` only.
- e2e tests run against the full real stack (`make dev` running); `page.route` patterns must be `/api/`-anchored; a mocked subject is not verification.
- Commit after every task (small commits).

## File Structure (created/modified this plan)

```
chili_app/src/components/status/
  statusTokens.ts          NEW — one state→{tone,label,hint} map for KB/document/workflow states
  StatusChip.tsx           NEW — renders a status via the token map (wraps ui/Chip)
  formatters.ts            NEW — formatTimestamp / formatRelativeTime / formatFileSize (single home)
  ConfirmDialog.tsx        NEW — confirmation dialog (plain + typed-name variants)
  __tests__/               NEW — vitest for all of the above
chili_app/src/stores/ingestionStudioStore.ts    REWRITE — drafts keyed by KB id
chili_app/src/components/ingestion/DocumentSourcePanel.tsx  MODIFY — append/remove/reset/accept
chili_app/src/components/ingestion/RunTimeline.tsx          MODIFY — server receipts, relative time
chili_app/src/components/knowledgebase/ScoreRunStatusPanel.tsx MODIFY — timestamps, disabled reason
chili_app/src/components/ingestion/SubmitPanel.tsx          MODIFY — disabled reason text, tone fix
chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx MODIFY — confirm delete, drop dup helper
chili_app/src/pages/KnowledgeBaseManagerPage.tsx            MODIFY — throughout
chili_app/src/pages/pages.css                               MODIFY — :disabled rules
chili_app/src/components/ingestion/ingestion.css            MODIFY — parse-button :disabled
chili_app/src/api/knowledgebases.ts                         MODIFY — status filter param
backend/api/routers/records.py                              MODIFY — receipt onto workflow metadata
backend/api/_workflow_projection.py                         MODIFY — parse receipt into response
backend/api/contracts.py                                    MODIFY — WorkflowRunResponse.receipt
backend/tests/api/test_workflows_receipt.py                 NEW
chili_app/e2e/ingestion-truth-safety.spec.ts                NEW
```

---

### Task 1: Status formatters — one home for timestamps and file sizes

**Files:**
- Create: `chili_app/src/components/status/formatters.ts`
- Test: `chili_app/src/components/status/__tests__/formatters.test.ts`

**Interfaces:**
- Produces: `formatTimestamp(value: string | null): string` (absolute local, e.g. "Aug 14, 2026, 4:33 PM"; `'Not yet recorded'` for null), `formatRelativeTime(value: string | null, now?: Date): string` ("just now" / "4m ago" / "3h ago" / falls back to `formatTimestamp` beyond 24h), `formatFileSize(sizeBytes: number | null | undefined): string` ("579 B" / "1.4 KB" / "2.3 MB"; `'Unknown size'` otherwise).

- [ ] **Step 1: Write the failing test**

```ts
// chili_app/src/components/status/__tests__/formatters.test.ts
import { describe, expect, it } from 'vitest'

import { formatFileSize, formatRelativeTime, formatTimestamp } from '../formatters'

describe('formatTimestamp', () => {
  it('formats an ISO string as local medium date + short time', () => {
    expect(formatTimestamp('2026-08-14T20:33:01.208754Z')).toMatch(/Aug 14, 2026/)
  })
  it('returns placeholder for null', () => {
    expect(formatTimestamp(null)).toBe('Not yet recorded')
  })
})

describe('formatRelativeTime', () => {
  const now = new Date('2026-08-14T21:00:00Z')
  it('says just now under a minute', () => {
    expect(formatRelativeTime('2026-08-14T20:59:40Z', now)).toBe('just now')
  })
  it('uses minutes under an hour', () => {
    expect(formatRelativeTime('2026-08-14T20:44:00Z', now)).toBe('16m ago')
  })
  it('uses hours under a day', () => {
    expect(formatRelativeTime('2026-08-14T18:00:00Z', now)).toBe('3h ago')
  })
  it('falls back to absolute beyond 24h', () => {
    expect(formatRelativeTime('2026-08-01T18:00:00Z', now)).toMatch(/Aug 1, 2026/)
  })
  it('returns placeholder for null', () => {
    expect(formatRelativeTime(null, now)).toBe('Not yet recorded')
  })
})

describe('formatFileSize', () => {
  it('formats bytes, KB, MB', () => {
    expect(formatFileSize(579)).toBe('579 B')
    expect(formatFileSize(1442)).toBe('1.4 KB')
    expect(formatFileSize(2.3 * 1024 * 1024)).toBe('2.3 MB')
  })
  it('handles null/undefined/zero', () => {
    expect(formatFileSize(null)).toBe('Unknown size')
    expect(formatFileSize(undefined)).toBe('Unknown size')
    expect(formatFileSize(0)).toBe('Unknown size')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chili_app && npx vitest run src/components/status/__tests__/formatters.test.ts`
Expected: FAIL — cannot resolve `../formatters`

- [ ] **Step 3: Write the implementation**

```ts
// chili_app/src/components/status/formatters.ts
const absoluteFormat = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

export function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'Not yet recorded'
  }
  return absoluteFormat.format(new Date(value))
}

/** Relative time for timelines: "just now" / "16m ago" / "3h ago", absolute beyond 24h. */
export function formatRelativeTime(value: string | null, now: Date = new Date()): string {
  if (!value) {
    return 'Not yet recorded'
  }
  const elapsedMs = now.getTime() - new Date(value).getTime()
  const minutes = Math.floor(elapsedMs / 60_000)
  if (minutes < 1) {
    return 'just now'
  }
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  return formatTimestamp(value)
}

export function formatFileSize(sizeBytes: number | null | undefined): string {
  if (!sizeBytes) {
    return 'Unknown size'
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`
  }
  if (sizeBytes < 1024 * 1024) {
    return `${(sizeBytes / 1024).toFixed(1)} KB`
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chili_app && npx vitest run src/components/status/__tests__/formatters.test.ts`
Expected: PASS (all 10)

- [ ] **Step 5: Commit**

```bash
git add chili_app/src/components/status/
git commit -m "feat(status): shared timestamp/file-size formatters"
```

---

### Task 2: StatusChip primitive + status token map

**Files:**
- Create: `chili_app/src/components/status/statusTokens.ts`
- Create: `chili_app/src/components/status/StatusChip.tsx`
- Test: `chili_app/src/components/status/__tests__/StatusChip.test.tsx`

**Interfaces:**
- Consumes: `Chip` from `chili_app/src/components/ui/Chip.tsx` (props: `label: string`, `tone`, optional `title`).
- Produces: `statusToken(kind: StatusKind, status: string): StatusToken` where `type StatusKind = 'knowledge-base' | 'document' | 'workflow'` and `type StatusToken = { label: string; tone: 'default' | 'info' | 'success' | 'warning' | 'danger' | 'network'; hint: string }`; `<StatusChip kind status />` renders the token via `Chip` with `title=hint`.

**Token table to encode** (KB copy comes verbatim from `chili_app/src/utils/knowledgeBaseStatus.ts` — reuse its `STATUS_COPY`, do not duplicate the strings; document/workflow rows are new):

| kind | status | label | tone | hint |
|---|---|---|---|---|
| document | pending/parsing/parsed/chunked/extracted | In progress | warning | Ingestion is still processing this document. |
| document | validated | Validated | success | Extraction finished and validated entities landed in the graph. |
| document | extracted_empty | No entities | default | Parsed cleanly but no domain entities were found — it contributed nothing to the graph. |
| document | failed | Failed | danger | Ingestion failed; see the error on this row. |
| workflow | queued | Queued | info | Waiting for the worker to pick this run up. |
| workflow | running | Running | warning | The pipeline is executing. |
| workflow | awaiting_approval | Awaiting approval | info | Parked at a human approval gate. |
| workflow | completed | Completed | success | All steps finished. |
| workflow | failed | Failed | danger | A step failed; the timeline shows which. |
| workflow | cancelled | Cancelled | default | Stopped before completion. |

Unknown statuses render sentence-cased with tone `default` and hint `''` (mirror the `humanize` fallback in `knowledgeBaseStatus.ts`).

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/components/status/__tests__/StatusChip.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { StatusChip } from '../StatusChip'
import { statusToken } from '../statusTokens'

describe('statusToken', () => {
  it('maps document extracted_empty to a distinct neutral state', () => {
    const token = statusToken('document', 'extracted_empty')
    expect(token.label).toBe('No entities')
    expect(token.tone).toBe('default')
  })
  it('maps document failed to danger', () => {
    expect(statusToken('document', 'failed').tone).toBe('danger')
  })
  it('reuses KB copy: active reads Empty', () => {
    expect(statusToken('knowledge-base', 'active').label).toBe('Empty')
  })
  it('sentence-cases unknown statuses', () => {
    expect(statusToken('workflow', 'some_new_state').label).toBe('Some new state')
  })
})

describe('StatusChip', () => {
  it('renders label and hint', () => {
    render(<StatusChip kind="document" status="extracted_empty" />)
    const chip = screen.getByText('No entities')
    expect(chip.closest('[title]')?.getAttribute('title')).toContain('contributed nothing')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chili_app && npx vitest run src/components/status/__tests__/StatusChip.test.tsx`
Expected: FAIL — cannot resolve `../StatusChip`

- [ ] **Step 3: Write the implementation**

```ts
// chili_app/src/components/status/statusTokens.ts
import {
  knowledgeBaseStatusHint,
  knowledgeBaseStatusLabel,
} from '../../utils/knowledgeBaseStatus'

export type StatusKind = 'knowledge-base' | 'document' | 'workflow'
export type StatusTone = 'default' | 'info' | 'success' | 'warning' | 'danger' | 'network'
export type StatusToken = { label: string; tone: StatusTone; hint: string }

const DOCUMENT_TOKENS: Record<string, StatusToken> = {
  pending: inProgress(),
  parsing: inProgress(),
  parsed: inProgress(),
  chunked: inProgress(),
  extracted: inProgress(),
  validated: {
    label: 'Validated',
    tone: 'success',
    hint: 'Extraction finished and validated entities landed in the graph.',
  },
  extracted_empty: {
    label: 'No entities',
    tone: 'default',
    hint: 'Parsed cleanly but no domain entities were found — it contributed nothing to the graph.',
  },
  failed: {
    label: 'Failed',
    tone: 'danger',
    hint: 'Ingestion failed; see the error on this row.',
  },
}

const WORKFLOW_TOKENS: Record<string, StatusToken> = {
  queued: { label: 'Queued', tone: 'info', hint: 'Waiting for the worker to pick this run up.' },
  running: { label: 'Running', tone: 'warning', hint: 'The pipeline is executing.' },
  awaiting_approval: {
    label: 'Awaiting approval',
    tone: 'info',
    hint: 'Parked at a human approval gate.',
  },
  completed: { label: 'Completed', tone: 'success', hint: 'All steps finished.' },
  failed: { label: 'Failed', tone: 'danger', hint: 'A step failed; the timeline shows which.' },
  cancelled: { label: 'Cancelled', tone: 'default', hint: 'Stopped before completion.' },
}

const KB_TONES: Record<string, StatusTone> = {
  ready: 'success',
  active: 'warning',
  building: 'warning',
  error: 'danger',
  archived: 'default',
}

function inProgress(): StatusToken {
  return {
    label: 'In progress',
    tone: 'warning',
    hint: 'Ingestion is still processing this document.',
  }
}

function sentenceCase(status: string): string {
  const spaced = status.replace(/_/g, ' ')
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function statusToken(kind: StatusKind, status: string): StatusToken {
  if (kind === 'knowledge-base') {
    return {
      label: knowledgeBaseStatusLabel(status),
      tone: KB_TONES[status] ?? 'default',
      hint: knowledgeBaseStatusHint(status),
    }
  }
  const table = kind === 'document' ? DOCUMENT_TOKENS : WORKFLOW_TOKENS
  return table[status] ?? { label: sentenceCase(status), tone: 'default', hint: '' }
}
```

```tsx
// chili_app/src/components/status/StatusChip.tsx
import { Chip } from '../ui/Chip'
import { statusToken } from './statusTokens'
import type { StatusKind } from './statusTokens'

export function StatusChip({ kind, status }: { kind: StatusKind; status: string }) {
  const token = statusToken(kind, status)
  return (
    <span title={token.hint || undefined}>
      <Chip label={token.label} tone={token.tone} />
    </span>
  )
}
```

Note: `knowledgeBaseStatusLabel`/`knowledgeBaseStatusHint` in `chili_app/src/utils/knowledgeBaseStatus.ts` are currently typed to the KB status union — if their parameter type is narrower than `string`, widen it to `string` there (the file already has a `humanize` fallback for unknown keys).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chili_app && npx vitest run src/components/status/__tests__/StatusChip.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add chili_app/src/components/status/ chili_app/src/utils/knowledgeBaseStatus.ts
git commit -m "feat(status): StatusChip primitive with one state->tone/label/hint map"
```

---

### Task 3: Kill raw ISO timestamps and duplicated helpers

**Files:**
- Modify: `chili_app/src/components/ingestion/RunTimeline.tsx` (raw `{workflow.updated_at}` around line 257)
- Modify: `chili_app/src/components/knowledgebase/ScoreRunStatusPanel.tsx` (raw `{run.updated_at}` around line 99)
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (delete local `formatTimestamp` :995-1004, `formatFileSize` :1006-1020, `toneForKnowledgeBaseStatus` :1022-1034, `toneForDocumentStatus` :1036-1044)
- Modify: `chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx` (delete its duplicate `toneForKnowledgeBaseStatus` at :35, use `StatusChip kind="knowledge-base"`)
- Modify: `chili_app/src/components/ingestion/DocumentSourcePanel.tsx` (delete local `formatFileSize` :10, import from status/formatters)

**Interfaces:**
- Consumes: Task 1 formatters, Task 2 `StatusChip`.

- [ ] **Step 1: Replace raw timestamps.** In `RunTimeline.tsx`, render `formatRelativeTime(workflow.updated_at)` where the raw string was, and add `title={workflow.updated_at}` on the element so the exact instant is hover-recoverable. Same treatment in `ScoreRunStatusPanel.tsx` for `run.updated_at`. Timelines use relative time; keep `formatTimestamp` for KB `created_at` and document rows in the page.

- [ ] **Step 2: Delete every duplicated helper** listed above; update all call sites to import from `../status/formatters` (or `../../components/status/formatters` from the page) and to render `<StatusChip kind="knowledge-base" status={...}/>` / `<StatusChip kind="document" status={...}/>` where the tone helpers were used. The document inventory chip keeps rendering `document.status` for now (Task 9 switches it to `current_status`).

- [ ] **Step 3: Verify no orphans**

Run: `cd chili_app && grep -rn "toneForKnowledgeBaseStatus\|toneForDocumentStatus" src/ ; npm run lint && npx tsc -b`
Expected: grep finds nothing; lint + typecheck clean.

- [ ] **Step 4: Run the existing unit suites** (they assert on rendered output and will catch label regressions)

Run: `cd chili_app && npm run test:run`
Expected: PASS (update any test asserting the raw ISO string to expect the relative form)

- [ ] **Step 5: Commit**

```bash
git add -A chili_app/src
git commit -m "fix(ingestion): relative timestamps in timelines; collapse duplicated tone/format helpers"
```

---

### Task 4: `:disabled` styling + disabled controls explain themselves

**Files:**
- Modify: `chili_app/src/pages/pages.css` (`.page-button` block at :170-212)
- Modify: `chili_app/src/components/ingestion/ingestion.css` (`.ingestion-records-source__parse` ~:450-460)
- Modify: `chili_app/src/components/ingestion/SubmitPanel.tsx`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (score-run `startTitle` :668-672)
- Modify: `chili_app/src/components/knowledgebase/ScoreRunStatusPanel.tsx`
- Test: extend `chili_app/src/components/ingestion/__tests__/SubmitPanel.test.tsx` (or create it if absent)

- [ ] **Step 1: CSS.** Append to `pages.css` after the `.page-button--primary:hover` rule:

```css
.page-button:disabled,
.page-list-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  filter: none;
}

.page-button:disabled:hover,
.page-list-item:disabled:hover {
  background: rgba(0, 212, 255, 0.08);
  border-color: rgba(0, 212, 255, 0.22);
}

.page-button--secondary:disabled:hover {
  background: rgba(136, 153, 187, 0.08);
  border-color: rgba(136, 153, 187, 0.22);
}

.page-button--primary:disabled,
.page-button--primary:disabled:hover {
  background: var(--c-cyan);
  border-color: var(--c-cyan);
  filter: saturate(0.4) brightness(0.8);
}
```

And guard the existing hover rule: change `.page-button:hover, .page-list-item:hover` (pages.css:187) to `.page-button:hover:not(:disabled), .page-list-item:hover:not(:disabled)`. In `ingestion.css`, add the same opacity/cursor treatment for `.ingestion-records-source__parse:disabled`.

- [ ] **Step 2: SubmitPanel truth.** In `SubmitPanel.tsx`: change the chip tone line so ready state reads as ready — `const tone = runPending ? 'info' : canRunIngestion ? 'success' : 'warning'`. The chip already names the missing prerequisite ("Select documents"/"Parse records"/"Select source type") — that satisfies "explain why disabled" for this control; no tooltip needed.

- [ ] **Step 3: Score-run reason honesty.** In `KnowledgeBaseManagerPage.tsx`, replace the always-entity-count `startTitle` with a reason that matches the actual blocker, and pass it as visible text:

```tsx
const scoreRunStartReason = !activeKnowledgeBaseId
  ? 'Select a knowledge base first.'
  : !knowledgeBase || knowledgeBase.entity_count === 0
    ? 'Start requires ingested entities in this knowledge base.'
    : null
```

Pass `startReason={scoreRunStartReason}` to `ScoreRunStatusPanel` (replacing `startTitle`); in `ScoreRunStatusPanel.tsx` render it adjacent to the Start button when non-null: `{startReason ? <p className="metric-row__label" role="note">{startReason}</p> : null}` — not a `title` tooltip.

- [ ] **Step 4: Test**

```tsx
// in SubmitPanel test file
it('explains why Run ingestion is disabled and marks the ready state green', () => {
  const { rerender } = render(
    <SubmitPanel sourceType="documents" canRunIngestion={false} runPending={false} onRunIngestion={() => {}} />,
  )
  expect(screen.getByRole('button', { name: 'Run ingestion' })).toBeDisabled()
  expect(screen.getByText('Select documents')).toBeInTheDocument()
  rerender(
    <SubmitPanel sourceType="documents" canRunIngestion runPending={false} onRunIngestion={() => {}} />,
  )
  expect(screen.getByText('Documents ready')).toBeInTheDocument()
})
```

Run: `cd chili_app && npm run test:run -- SubmitPanel`
Expected: PASS

- [ ] **Step 5: Visual check against the running stack** (project rule: run the app when changing frontend behavior). With `make dev` up, load `http://localhost:5173/knowledge-bases`, confirm a disabled "Run ingestion"/"Start score-all" is visibly dimmed, keeps `not-allowed` cursor, and does not brighten on hover. Screenshot for the PR.

- [ ] **Step 6: Commit**

```bash
git add -A chili_app/src
git commit -m "fix(ui): disabled buttons look disabled and explain why"
```

---

### Task 5: ConfirmDialog + guarded destructive actions

**Files:**
- Create: `chili_app/src/components/status/ConfirmDialog.tsx`
- Test: `chili_app/src/components/status/__tests__/ConfirmDialog.test.tsx`
- Modify: `chili_app/src/components/ingestion/KnowledgeBaseSelector.tsx` (delete button :153-162)
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` ("Remove document" :928-937)

**Interfaces:**
- Produces:

```tsx
type ConfirmDialogProps = {
  open: boolean
  title: string
  body: string                 // states the blast radius
  confirmLabel: string
  confirmTypedText?: string    // when set, confirm stays disabled until the user types this exactly
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}
export function ConfirmDialog(props: ConfirmDialogProps): JSX.Element | null
```

Implementation notes: render `null` when `!open`; use a `<dialog>`-free portal-less inline overlay (`role="dialog"`, `aria-modal="true"`, focus the cancel button on open, Escape → `onCancel`); typed-name input compares trimmed exact match; confirm button is `page-button page-button--primary` with `disabled` until match. Style with existing `page-*` classes plus a small `.confirm-dialog` overlay block appended to `pages.css`.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/components/status/__tests__/ConfirmDialog.test.tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmDialog } from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <ConfirmDialog open={false} title="t" body="b" confirmLabel="Delete" onConfirm={() => {}} onCancel={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('gates confirm behind typed text', async () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        open
        title="Delete knowledge base"
        body="Deletes 8 documents, 53 entities, and all runs."
        confirmLabel="Delete knowledge base"
        confirmTypedText="Jimmy_Dean"
        destructive
        onConfirm={onConfirm}
        onCancel={() => {}}
      />,
    )
    const confirm = screen.getByRole('button', { name: 'Delete knowledge base' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByRole('textbox'), 'Jimmy_Dean')
    expect(confirm).toBeEnabled()
    await userEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('cancels on Escape', async () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog open title="t" body="b" confirmLabel="Remove" onConfirm={() => {}} onCancel={onCancel} />,
    )
    await userEvent.keyboard('{Escape}')
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run to verify FAIL**, then implement `ConfirmDialog.tsx` per the interface notes above, then run to PASS: `cd chili_app && npx vitest run src/components/status/__tests__/ConfirmDialog.test.tsx`

- [ ] **Step 3: Wire the KB delete.** In `KnowledgeBaseManagerPage.tsx`, add `const [confirmingKbDelete, setConfirmingKbDelete] = useState(false)`. `KnowledgeBaseSelector`'s `onDelete` now only sets `confirmingKbDelete(true)`. Render, next to the selector card:

```tsx
<ConfirmDialog
  open={confirmingKbDelete}
  title="Delete knowledge base"
  body={
    knowledgeBase
      ? `Deletes ${knowledgeBase.document_count} documents, ${knowledgeBase.entity_count} entities, ${knowledgeBase.relationship_count} relationships, and all runs. This cannot be undone.`
      : 'This cannot be undone.'
  }
  confirmLabel="Delete knowledge base"
  confirmTypedText={knowledgeBase?.name}
  destructive
  onCancel={() => setConfirmingKbDelete(false)}
  onConfirm={() => {
    setConfirmingKbDelete(false)
    if (activeKnowledgeBaseId) {
      deleteKnowledgeBaseMutation.mutate(activeKnowledgeBaseId, { onSuccess: /* existing handler body */ })
    }
  }}
/>
```

- [ ] **Step 4: Wire the document remove** the same way with a plain (non-typed) dialog: `title="Remove document"`, `body` = `` `Removes ${activeDocument?.filename ?? 'this document'} and its graph and vector artifacts.` ``, no `confirmTypedText`.

- [ ] **Step 5: Update the page unit test** (`chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`): any test clicking delete now asserts the dialog appears and confirms through it. Run `cd chili_app && npm run test:run` → PASS.

- [ ] **Step 6: Commit**

```bash
git add -A chili_app/src
git commit -m "feat(ingestion): confirmation dialogs for KB and document deletion"
```

---

### Task 6: Document staging — append, per-file remove, input reset, accept filter

**Files:**
- Modify: `chili_app/src/components/ingestion/DocumentSourcePanel.tsx`
- Test: `chili_app/src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx` (create if absent)
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (pass `acceptContentTypes`)

**Interfaces:**
- Produces: `DocumentSourcePanel` props become `{ files: File[]; onFilesChange: (files: File[]) => void; acceptContentTypes?: string[] }`. Behavior contract: a picker event **appends** (deduped by `name + size + lastModified`); each staged row gets a "Remove" button; both inputs set `event.currentTarget.value = ''` after reading files (so re-picking a corrected same-named file fires change); the file input carries `accept={acceptContentTypes?.join(',')}`.

- [ ] **Step 1: Write the failing test**

```tsx
// chili_app/src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { DocumentSourcePanel } from '../DocumentSourcePanel'

function makeFile(name: string): File {
  return new File(['x'], name, { type: 'application/json' })
}

describe('DocumentSourcePanel staging', () => {
  it('appends new picks to the existing staged list', () => {
    const onFilesChange = vi.fn()
    const staged = [makeFile('a.json')]
    render(<DocumentSourcePanel files={staged} onFilesChange={onFilesChange} />)
    fireEvent.change(screen.getByLabelText('Document files'), {
      target: { files: [makeFile('b.json')] },
    })
    const next = onFilesChange.mock.calls[0][0] as File[]
    expect(next.map((f) => f.name)).toEqual(['a.json', 'b.json'])
  })

  it('dedupes re-picks of an already staged file', () => {
    const onFilesChange = vi.fn()
    const a = makeFile('a.json')
    render(<DocumentSourcePanel files={[a]} onFilesChange={onFilesChange} />)
    fireEvent.change(screen.getByLabelText('Document files'), { target: { files: [a] } })
    expect((onFilesChange.mock.calls[0][0] as File[]).length).toBe(1)
  })

  it('removes a single staged file', async () => {
    const onFilesChange = vi.fn()
    render(
      <DocumentSourcePanel files={[makeFile('a.json'), makeFile('b.json')]} onFilesChange={onFilesChange} />,
    )
    await userEvent.click(screen.getAllByRole('button', { name: /remove/i })[0])
    expect((onFilesChange.mock.calls[0][0] as File[]).map((f) => f.name)).toEqual(['b.json'])
  })

  it('passes accept through to the file input', () => {
    render(
      <DocumentSourcePanel files={[]} onFilesChange={() => {}} acceptContentTypes={['application/pdf', 'text/csv']} />,
    )
    expect(screen.getByLabelText('Document files')).toHaveAttribute('accept', 'application/pdf,text/csv')
  })
})
```

- [ ] **Step 2: Run to verify FAIL** (`npx vitest run src/components/ingestion/__tests__/DocumentSourcePanel.test.tsx`)

- [ ] **Step 3: Implement.** Inside `DocumentSourcePanel`, replace both `onChange` handlers with:

```tsx
function stageMore(event: ChangeEvent<HTMLInputElement>) {
  const picked = Array.from(event.currentTarget.files ?? [])
  event.currentTarget.value = ''
  if (picked.length === 0) {
    return
  }
  const known = new Set(files.map(fileKey))
  onFilesChange([...files, ...picked.filter((file) => !known.has(fileKey(file)))])
}

function removeFile(target: File) {
  onFilesChange(files.filter((file) => fileKey(file) !== fileKey(target)))
}
```

with `const fileKey = (f: File) => `${f.name}:${f.size}:${f.lastModified}`` at module scope. Add `accept={acceptContentTypes?.join(',')}` to the file input (not the folder input — directory pickers ignore accept). In the staged list rows, add `<button type="button" className="page-button page-button--sm page-button--secondary" onClick={() => removeFile(file)}>Remove {fileLabel(file)}</button>` (aria-name includes the filename).

- [ ] **Step 4: Pass the accept list from the page:** in `KnowledgeBaseManagerPage.tsx`, `<DocumentSourcePanel ... acceptContentTypes={domainConfigQuery.data?.validation?.allowed_content_types} />`.

- [ ] **Step 5: Run to PASS**, then full suite: `cd chili_app && npm run test:run && npm run lint`

- [ ] **Step 6: Commit**

```bash
git add -A chili_app/src
git commit -m "fix(ingestion): file staging appends with per-file remove and input reset"
```

---

### Task 7: Draft store keyed by knowledge base

**Files:**
- Rewrite: `chili_app/src/stores/ingestionStudioStore.ts`
- Test: `chili_app/src/stores/__tests__/ingestionStudioStore.test.ts` (rewrite)
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (all `studio.*` draft reads/writes)

**Interfaces:**
- Produces:

```ts
export type IngestionDraft = {
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  pendingRecordFile: File | null
  parsedRows: Record<string, unknown>[]
  validationIssues: ValidationIssue[]
}
export const emptyDraft: () => IngestionDraft
// Store shape:
type IngestionStudioState = {
  currentStep: IngestionStepId                    // page chrome, not per-KB (stepper dies in Phase 2)
  draftsByKb: Record<string, IngestionDraft>
  setCurrentStep(step: IngestionStepId): void
  updateDraft(kbId: string, patch: Partial<IngestionDraft>): void
  addValidationIssues(kbId: string, issues: ValidationIssue[]): void
  clearDraft(kbId: string): void
  reset(): void
}
// Convenience hook (same file):
export function useIngestionDraft(kbId: string | null): IngestionDraft  // returns emptyDraft() when kbId null/absent
```

`receipts`, `addReceipt`, `activeTimelineEntryId`, `setActiveTimelineEntryId` are **deleted** (Task 8 removes their consumers first if executing out of order — execute Tasks 7 and 8 together in one PR if needed; Task 8 depends on Task 7's store shape). `IngestionReceiptEntry` and `TimelineEntry` in `chili_app/src/lib/ingestion/types.ts` are deleted in Task 8.

- [ ] **Step 1: Write the failing test**

```ts
// chili_app/src/stores/__tests__/ingestionStudioStore.test.ts (replace existing)
import { beforeEach, describe, expect, it } from 'vitest'

import { emptyDraft, useIngestionStudioStore } from '../ingestionStudioStore'

describe('ingestionStudioStore drafts are scoped by knowledge base', () => {
  beforeEach(() => useIngestionStudioStore.getState().reset())

  it('a draft staged for KB A never appears under KB B', () => {
    const file = new File(['x'], 'a.json', { type: 'application/json' })
    useIngestionStudioStore.getState().updateDraft('kb-a', { pendingFiles: [file], sourceType: 'documents' })
    const state = useIngestionStudioStore.getState()
    expect(state.draftsByKb['kb-a'].pendingFiles).toHaveLength(1)
    expect(state.draftsByKb['kb-b']).toBeUndefined()
  })

  it('clearDraft removes exactly one KB draft', () => {
    const store = useIngestionStudioStore.getState()
    store.updateDraft('kb-a', { selectedFeedName: 'pde' })
    store.updateDraft('kb-b', { selectedFeedName: 'nppes_providers' })
    store.clearDraft('kb-a')
    const state = useIngestionStudioStore.getState()
    expect(state.draftsByKb['kb-a']).toBeUndefined()
    expect(state.draftsByKb['kb-b'].selectedFeedName).toBe('nppes_providers')
  })

  it('addValidationIssues appends within the right draft', () => {
    const store = useIngestionStudioStore.getState()
    store.updateDraft('kb-a', {})
    store.addValidationIssues('kb-a', [
      { id: 'x', source: 'backend', severity: 'error', message: 'boom' },
    ])
    expect(useIngestionStudioStore.getState().draftsByKb['kb-a'].validationIssues).toHaveLength(1)
  })

  it('emptyDraft is the fallback shape', () => {
    expect(emptyDraft().pendingFiles).toEqual([])
    expect(emptyDraft().sourceType).toBeNull()
  })
})
```

- [ ] **Step 2: Run to FAIL**, then rewrite the store:

```ts
// chili_app/src/stores/ingestionStudioStore.ts (full replacement)
import { create } from 'zustand'

import type {
  IngestionSourceType,
  IngestionStepId,
  ValidationIssue,
} from '../lib/ingestion/types'

export type IngestionDraft = {
  sourceType: IngestionSourceType | null
  selectedFeedName: string | null
  pendingFiles: File[]
  pendingRecordFile: File | null
  parsedRows: Record<string, unknown>[]
  validationIssues: ValidationIssue[]
}

export const emptyDraft = (): IngestionDraft => ({
  sourceType: null,
  selectedFeedName: null,
  pendingFiles: [],
  pendingRecordFile: null,
  parsedRows: [],
  validationIssues: [],
})

type IngestionStudioState = {
  currentStep: IngestionStepId
  draftsByKb: Record<string, IngestionDraft>
  setCurrentStep: (currentStep: IngestionStepId) => void
  updateDraft: (kbId: string, patch: Partial<IngestionDraft>) => void
  addValidationIssues: (kbId: string, issues: ValidationIssue[]) => void
  clearDraft: (kbId: string) => void
  reset: () => void
}

export const useIngestionStudioStore = create<IngestionStudioState>((set) => ({
  currentStep: 'knowledge-base',
  draftsByKb: {},
  setCurrentStep: (currentStep) => set({ currentStep }),
  updateDraft: (kbId, patch) =>
    set((state) => ({
      draftsByKb: {
        ...state.draftsByKb,
        [kbId]: { ...(state.draftsByKb[kbId] ?? emptyDraft()), ...patch },
      },
    })),
  addValidationIssues: (kbId, issues) =>
    set((state) => {
      const draft = state.draftsByKb[kbId] ?? emptyDraft()
      return {
        draftsByKb: {
          ...state.draftsByKb,
          [kbId]: { ...draft, validationIssues: [...draft.validationIssues, ...issues] },
        },
      }
    }),
  clearDraft: (kbId) =>
    set((state) => {
      const { [kbId]: _removed, ...rest } = state.draftsByKb
      return { draftsByKb: rest }
    }),
  reset: () => set({ currentStep: 'knowledge-base', draftsByKb: {} }),
}))

/** Draft for the given KB, or an empty draft when no KB is selected. */
export function useIngestionDraft(kbId: string | null): IngestionDraft {
  return useIngestionStudioStore((state) =>
    kbId ? state.draftsByKb[kbId] ?? EMPTY_DRAFT_SINGLETON : EMPTY_DRAFT_SINGLETON,
  )
}

// Stable identity so the selector doesn't return a new object per render.
const EMPTY_DRAFT_SINGLETON: IngestionDraft = emptyDraft()
```

- [ ] **Step 3: Rewire the page.** In `KnowledgeBaseManagerPage.tsx`: `const draft = useIngestionDraft(activeKnowledgeBaseId)`; `const updateDraft = useIngestionStudioStore((s) => s.updateDraft)`; `const clearDraft = useIngestionStudioStore((s) => s.clearDraft)`; `const setCurrentStep = useIngestionStudioStore((s) => s.setCurrentStep)` — selector subscriptions only, delete the bare `useIngestionStudioStore()` call. Mechanical mapping: `studio.pendingFiles` → `draft.pendingFiles`; `studio.setPendingFiles(x)` → `activeKnowledgeBaseId && updateDraft(activeKnowledgeBaseId, { pendingFiles: x })`; likewise sourceType/selectedFeedName/pendingRecordFile/parsedRows/validationIssues. On upload success handlers (documents :188-204, record file :229-243, push :320-331): `clearDraft(activeKnowledgeBaseId)` instead of piecemeal clears. On KB delete success: `clearDraft(<deleted id>)`. Source panels must be disabled until a KB is selected: wrap the Step-1 card content in `{activeKnowledgeBaseId ? (...) : <EmptyState title="Select a knowledge base" description="Drafts are staged per knowledge base." />}` so `updateDraft` never needs a null kbId.

- [ ] **Step 4: Run all frontend tests + typecheck:** `cd chili_app && npm run test:run && npx tsc -b && npm run lint`. The page test file will need the same mechanical renames. Expected: PASS/clean.

- [ ] **Step 5: Manual verification on the running stack:** stage a file under KB A, switch to KB B in the selector → staging area is empty; switch back → file still staged. This is the regression that motivated the task.

- [ ] **Step 6: Commit**

```bash
git add -A chili_app/src
git commit -m "fix(ingestion): draft state keyed by knowledge base — cross-KB leakage unrepresentable"
```

---

### Task 8 (backend + contracts): record receipts ride on their workflow run

**Files:**
- Modify: `backend/api/routers/records.py` (`_start_records_workflow` :89-112)
- Modify: `backend/api/contracts.py` (`WorkflowRunResponse` :1634-1646)
- Modify: `backend/api/_workflow_projection.py` (response construction :45)
- Test: Create `backend/tests/api/test_workflows_receipt.py`
- Then: regenerate `chili_app/openapi.json` + `npm run codegen:api`

**Interfaces:**
- Consumes: `WorkflowRun.metadata: dict[str, str|int|float|bool]` (`backend/agent/models.py:125`) — flat values only, so the receipt is stored as a JSON **string** under key `record_receipt_json`.
- Produces: `WorkflowRunResponse.receipt: RecordIngestReceipt | None` (reusing `backend/records/service_models.py:23` — already a public response model on the records routes). Frontend gains `WorkflowRunResponse['receipt']` after codegen.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/api/test_workflows_receipt.py
"""Record-ingest receipts must survive on the workflow run (spec §4.3)."""
from __future__ import annotations

import json

from api._workflow_projection import workflow_run_to_response
from agent.models import WorkflowRun, WorkflowStepState
from records.service_models import RecordIngestReceipt


def _run_with_metadata(metadata: dict[str, str]) -> WorkflowRun:
    return WorkflowRun(
        workflow_id="wf-1",
        knowledge_base_id="kb-1",
        trigger_event_type="records.ingested",
        steps=[WorkflowStepState(step_name="ingest")],
        metadata=metadata,
    )


def test_receipt_json_metadata_projects_to_typed_receipt() -> None:
    receipt = RecordIngestReceipt(
        knowledge_base_id="kb-1",
        feed_name="pde",
        record_type="prescription_event",
        correlation_id="corr-1",
        accepted_count=10,
        rejected_count=2,
        suppressed_existing_count=3,
    )
    run = _run_with_metadata(
        {"record_receipt_json": json.dumps(receipt.model_dump(mode="json"))}
    )
    response = workflow_run_to_response(run)
    assert response.receipt is not None
    assert response.receipt.accepted_count == 10
    assert response.receipt.suppressed_existing_count == 3


def test_missing_or_malformed_receipt_metadata_is_none() -> None:
    assert workflow_run_to_response(_run_with_metadata({})).receipt is None
    assert (
        workflow_run_to_response(
            _run_with_metadata({"record_receipt_json": "not json"})
        ).receipt
        is None
    )
```

Adjust the import/helper names to the actual ones in `_workflow_projection.py` (the response constructor lives at `_workflow_projection.py:45`; if the function has a different name, use it — the test's substance is the metadata→typed-receipt projection and the malformed-input fallback). If `WorkflowStepState` requires more fields, copy a minimal valid construction from an existing test in `backend/tests/api/` that builds a `WorkflowRun`.

- [ ] **Step 2: Run to FAIL:** `cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest tests/api/test_workflows_receipt.py -v`
Expected: FAIL — `WorkflowRunResponse` has no attribute `receipt`.

- [ ] **Step 3: Implement.**

In `backend/api/contracts.py`, add to `WorkflowRunResponse`:

```python
    # Record-ingest receipt for records-triggered runs; None for document runs.
    # Rides the run's flat metadata as a JSON string (agent metadata cannot
    # hold nested objects) and is re-typed here at the projection boundary.
    receipt: RecordIngestReceipt | None = None
```

with `from records.service_models import RecordIngestReceipt` (check for an existing import block from `records.`; follow the module's import conventions).

In `backend/api/_workflow_projection.py`, inside the response constructor:

```python
receipt: RecordIngestReceipt | None = None
raw_receipt = run.metadata.get("record_receipt_json")
if isinstance(raw_receipt, str):
    try:
        receipt = RecordIngestReceipt.model_validate_json(raw_receipt)
    except ValidationError:
        receipt = None  # older/foreign runs: absence, not an error
```

(`from pydantic import ValidationError`; `model_validate_json` also raises on non-JSON input, which is exactly the malformed case.) Pass `receipt=receipt` to `WorkflowRunResponse(...)`.

In `backend/api/routers/records.py` `_start_records_workflow`, add the receipt to the submission:

```python
    agent_service.start_workflow(
        WorkflowSubmissionRequest(
            knowledge_base_id=knowledge_base_id,
            trigger_event_type="records.ingested",
            requested_steps=default_steps_for_trigger("records.ingested"),
            correlation_id=correlation_id,
            metadata={
                "record_receipt_json": json.dumps(receipt.model_dump(mode="json"))
            },
        )
    )
```

(`import json` at top if absent. `WorkflowSubmissionRequest.metadata` exists — `agent/models.py:112`; the service copies it into the run at `agent/service.py:75`.)

- [ ] **Step 4: Run to PASS**, then the full backend gates:

```bash
cd backend && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov
backend/.venv/bin/ruff check --no-cache .   # from repo root
cd backend && .venv/bin/pyright
```

Expected: green, coverage ≥ 85%, pyright clean.

- [ ] **Step 5: Regenerate contracts** (frontend-consumed Pydantic change — mandatory):

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app && npm run codegen:api && npx tsc -b
```

Expected: `WorkflowRunResponse` in `chili_app/src/lib/api/schema.ts` gains `receipt`; typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add backend/ chili_app/openapi.json chili_app/src/lib/api/schema.ts chili_app/src/api/contracts.ts
git commit -m "feat(workflows): record-ingest receipts ride their workflow run"
```

---

### Task 9 (frontend): Runs timeline hydrates from the server; ghost receipt log dies

**Files:**
- Modify: `chili_app/src/components/ingestion/RunTimeline.tsx`
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (all `addReceipt` calls :195-201, :234-241, :322-329; `runTimelineVisible` :136-137; `RunTimeline` props :626-633)
- Modify: `chili_app/src/lib/ingestion/types.ts` (delete `IngestionReceiptEntry`, `TimelineEntry`)
- Test: `chili_app/src/components/ingestion/__tests__/RunTimeline.test.tsx` (update)

**Interfaces:**
- Consumes: `WorkflowRunResponse['receipt']` from Task 8's regenerated contracts.
- Produces: `RunTimeline` props become `{ workflows: WorkflowRunResponse[] }` (receipts prop deleted). `ReceiptDetails` (inline in RunTimeline.tsx:295) renders from `workflow.receipt` and now also shows suppressed rows: `` `${receipt.suppressed_existing_count} already existed (skipped)` `` when `> 0`.

- [ ] **Step 1: Update the RunTimeline test** to feed workflows carrying receipts and assert: (a) a records workflow renders its accepted/rejected/suppressed counts; (b) a workflow without a receipt (document run) renders no receipt block; (c) no `receipts` prop exists anymore (TypeScript enforces this — the test simply compiles against the new props).

```tsx
it('renders receipt counts from the workflow payload', () => {
  render(
    <RunTimeline
      workflows={[
        {
          ...baseWorkflow,           // reuse the file's existing fixture builder
          receipt: {
            knowledge_base_id: 'kb-1', feed_name: 'pde', record_type: 'prescription_event',
            correlation_id: 'corr-1', accepted_count: 10, duplicate: false, duplicate_count: 0,
            suppressed_existing_count: 3, rejected_count: 2, rejected: [], created_at: '2026-08-14T20:00:00Z',
          },
        },
      ]}
    />,
  )
  expect(screen.getByText(/10 accepted/)).toBeInTheDocument()
  expect(screen.getByText(/3 already existed/)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run to FAIL**, then implement: delete the receipts merge inside `RunTimeline.tsx` (the `TimelineItem` union keeps only the workflow arm), render `ReceiptDetails` when `workflow.receipt` is non-null, add the suppressed-count line. In the page: delete all three `studio.addReceipt(...)` blocks (the success toasts stay), change `runTimelineVisible` to `documents.length > 0 || workflows.length > 0`, pass only `workflows={workflows}`. Delete the two dead types from `lib/ingestion/types.ts`.

- [ ] **Step 3: Run to PASS + typecheck:** `cd chili_app && npm run test:run && npx tsc -b && npm run lint`

- [ ] **Step 4: Manual verification on the running stack:** upload a records CSV (fixtures in `~/uat_staging/records/`, feed `pde`), watch the timeline entry appear with counts, **refresh the page** — the receipt counts must survive reload (they come from `GET /api/workflows` now). This was impossible before.

- [ ] **Step 5: Commit**

```bash
git add -A chili_app/src
git commit -m "feat(ingestion): run timeline hydrates receipts from workflows; client ghost log removed"
```

---

### Task 10: Document inventory renders the durable lifecycle

**Files:**
- Modify: `chili_app/src/api/knowledgebases.ts` (`KnowledgeBaseDocumentsOptions` :16-19 — add `status?: string`)
- Modify: `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (`DocumentInventory` :835-977)
- Test: `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `DocumentSummary` fields already in the generated schema: `current_status`, `last_error`, `dropped_entity_count`, `dropped_relationship_count`, `drop_sample_reasons` (backend returns them today; the inventory's prop type at page:838-846 narrows them away — widen it to the contracts type). `StatusChip` from Task 2.
- Produces: inventory rows show `<StatusChip kind="document" status={document.current_status ?? document.status} />`; a `failed` row renders `last_error` inline (danger text, always visible); rows with drops render "`{kept} kept · {dropped} dropped`" where `kept = entity math is NOT available client-side` — render "`{dropped_entity_count} entities dropped`" instead (exact counts only; no invented math); warning reasons expand on an explicit "Show N warnings" toggle button per row (no hover-only `title`); a status `<select>` above the list filters via the API (`options: all/validated/extracted_empty/failed`, wired to `useKnowledgeBaseDocuments(kbId, { status })`).

- [ ] **Step 1: Extend the API client** — add `status` to `KnowledgeBaseDocumentsOptions` and thread it into the query string and query key in `chili_app/src/api/knowledgebases.ts` (mirror how `limit`/`offset` are threaded).

- [ ] **Step 2: Write failing tests** in the page test file: (a) a document with `current_status: 'failed'` and `last_error: 'boom'` renders "Failed" chip and the text "boom" without clicks; (b) a document with `current_status: 'extracted_empty'` renders "No entities" and not a success-toned "ready" chip; (c) clicking "Show 2 warnings" reveals the reasons list. Use the file's existing MSW/fixture pattern for the documents query.

- [ ] **Step 3: Run to FAIL, implement, run to PASS.** Implementation notes: widen `DocumentInventoryProps.documents` to `KnowledgeBaseDocumentsResponse['items']` from contracts; replace the status chip; the warnings toggle is per-row `useState<string | null>` (expanded row id) inside `DocumentInventory`; the filter select sits beside the "N tracked" chip; pass `{ status: statusFilter === 'all' ? undefined : statusFilter }`.

- [ ] **Step 4: Manual verification on the running stack:** the Jimmy_Dean UAT KB has 8 documents including `06_zero_entity_resume_like.txt` (`extracted_empty`) — verify it now reads "No entities" (neutral), the filter isolates it, and warnings expand without hover.

- [ ] **Step 5: Run gates:** `cd chili_app && npm run test:run && npx tsc -b && npm run lint`

- [ ] **Step 6: Commit**

```bash
git add -A chili_app/src
git commit -m "feat(ingestion): document inventory renders durable lifecycle, errors, and warning reasons"
```

---

### Task 11: e2e regression suite for Phase 1 (real stack)

**Files:**
- Create: `chili_app/e2e/ingestion-truth-safety.spec.ts`

**Interfaces:**
- Consumes: helper utilities in `chili_app/e2e/helpers/` (KB creation/cleanup — reuse the patterns from `knowledge-base-list.spec.ts` and `ingestion-records.spec.ts`; read both before writing). Fixture files: `docs/testing/knowledge_base_fixtures/medicare_fraud/01_single_claim_complete.json` and `06_zero_entity_resume_like.txt`, `backend/tests/e2e/fixtures/tiny_pde.csv`.

- [ ] **Step 1: Write the spec** covering, in one serial describe block against a fresh KB created via the UI:
  1. **Disabled affordance:** before staging anything, `Run ingestion` has `[disabled]` and the status chip reads "Select source type".
  2. **Staging append + remove:** stage `01_...json` via `setInputFiles`, stage `06_...txt` in a second `setInputFiles` call — assert BOTH filenames listed (append semantics); remove `01`, assert only `06` remains; re-stage `01`.
  3. **Run + timeline persistence:** run ingestion; wait for the timeline entry; `page.reload()`; assert the completed run is still in the timeline (server-hydrated).
  4. **Inventory truth:** assert `06_zero_entity_resume_like.txt` shows "No entities" (not "ready"); use the status filter to show only `extracted_empty` and assert the list shrinks to it.
  5. **Records receipt detail:** switch to Structured Records, upload `tiny_pde.csv` to feed `pde`, wait for the receipt in the timeline, reload, assert accepted-count text survives.
  6. **Cross-KB draft isolation:** create a second KB, stage a file, select the first KB — staging list is empty; select back — file still staged.
  7. **Guarded deletes:** click "Remove document" — dialog appears — cancel leaves the document; "Delete selected knowledge base" requires typing the KB name before the confirm button enables; confirm; assert redirect to the empty selector state. (This also cleans up the test KBs.)

- [ ] **Step 2: Run against the full stack** (stack must be up: `make dev`):

```bash
cd chili_app && npx playwright test e2e/ingestion-truth-safety.spec.ts
```

Expected: PASS. No `page.route` mocks anywhere in this spec.

- [ ] **Step 3: Run the whole e2e suite** to catch regressions in the existing ingestion specs (they assert on the old receipts/stepper behavior and may need updates — fix them, do not skip them): `npm run test:e2e` (or `make test-e2e` for the from-scratch stack variant).

- [ ] **Step 4: Commit**

```bash
git add chili_app/e2e
git commit -m "test(e2e): phase-1 truth-and-safety regression suite"
```

---

### Task 12: Documentation + final gates

**Files:**
- Modify: `chili_app/README.md` (Ingestion Studio section: draft-store-keyed-by-KB, server-hydrated receipts, confirm dialogs, document lifecycle rendering)
- Modify: `docs/architecture.md` (§8.2 store description: `ingestionStudioStore` is now per-KB drafts; timeline is server-hydrated)
- Modify: `.github/copilot-instructions.md` only if it references the old store/receipt behavior (grep first)

- [ ] **Step 1: Update the docs listed above.** Grep for stale claims: `grep -rn "ingestionStudioStore\|receipts" chili_app/README.md docs/architecture.md .github/`

- [ ] **Step 2: Full gate run** (everything, both sides):

```bash
backend/.venv/bin/ruff check --no-cache .
cd backend && .venv/bin/pyright && DATABASE_URL=postgresql://chili:chili@localhost:5432/chili_test .venv/bin/pytest --cov
cd chili_app && npm run lint && npx tsc -b && npm run test:run
make check
```

Expected: all green, coverage ≥ 85%.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: phase-1 ingestion truth-and-safety documentation updates"
```

---

## Self-Review (performed at write time)

- **Spec coverage (Phase 1 list, spec §8.1):** `:disabled` styles → Task 4; Status primitive + timestamps → Tasks 1-3; confirmations → Task 5; file-input append/remove/reset → Task 6; draft store keyed by KB → Task 7; receipts-from-workflows → Tasks 8-9; document `current_status`/`last_error`/drop counts → Task 10. e2e + docs → Tasks 11-12. Gaps: none.
- **Deliberately deferred to later phases:** stepper deletion, `Watch runs` fix, URL-owned selection (Phase 2); readiness chip semantics (Phase 3); multi-feed queue, precheck/replace warnings (Phase 4/3). The `setCurrentStep` call sites survive Phase 1 untouched.
- **Type consistency:** `useIngestionDraft(kbId)` / `updateDraft(kbId, patch)` / `clearDraft(kbId)` used identically in Tasks 7, 9, 11; `WorkflowRunResponse.receipt` named identically in Tasks 8-9; `StatusChip kind/status` identical in Tasks 2, 3, 10.
- **Placeholder scan:** each code step carries concrete code; the two "adjust to actual name" notes (Task 8 Step 1 projection helper, Task 11 helper reuse) point at exact files/lines to read, not TBDs.
