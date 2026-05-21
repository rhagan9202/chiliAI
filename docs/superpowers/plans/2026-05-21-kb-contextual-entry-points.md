# Contextual Knowledge Base Entry Points Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead-end no-KB empty states on Investigation Workbench and RAG Chat with actionable "+ Create Knowledge Base" CTAs, and give RAG Chat a real URL-synced KB picker that resets the in-progress thread when the user switches KB.

**Architecture:** Extend the shared `EmptyState` component with a single optional `action?: ReactNode` prop so both pages can render a primary button below the empty-state description. RAG Chat replaces its hardcoded `knowledgeBases[0]` selection with `useSearchParams`-driven state mirroring Investigation Workbench's existing pattern.

**Tech Stack:** React 19, TypeScript strict, Vite 8, React Router 6, Tanstack Query, Vitest + Testing Library + `@testing-library/user-event`, Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-05-21-kb-contextual-entry-points-design.md`

---

## Conventions Used Throughout

- All paths are relative to repo root unless prefixed with `/`.
- Commands run from `chili_app/` unless stated otherwise.
- Existing tests use `vi.mock('react-router-dom', ...)` with `vi.hoisted` mocks — match that pattern when extending them.
- Existing CSS classes to reuse: `.page-button` (primary action button — already styled `cyan`), `.feedback-state` (the empty-state container), `.metric-row`, `.metric-row__label`, `.page-input`, `.metric-stack`.
- The shared `Card` and `EmptyState` UI components live in `chili_app/src/components/ui/`.

---

## Task 1: Extend `EmptyState` with optional `action` prop

**Files:**
- Modify: `chili_app/src/components/ui/EmptyState.tsx`
- Modify: `chili_app/src/components/ui/ui.css`
- Create: `chili_app/src/components/ui/__tests__/EmptyState.test.tsx`

- [ ] **Step 1: Create the test directory and write the failing test**

Create `chili_app/src/components/ui/__tests__/EmptyState.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders title and description with no action when action prop is omitted', () => {
    render(
      <EmptyState
        title="No data"
        description="Nothing to show yet."
      />,
    )

    expect(screen.getByText('No data')).toBeInTheDocument()
    expect(screen.getByText('Nothing to show yet.')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders the action node below the description when supplied', () => {
    render(
      <EmptyState
        title="No KB"
        description="Create one to continue."
        action={<button type="button">Create Knowledge Base</button>}
      />,
    )

    expect(
      screen.getByRole('button', { name: 'Create Knowledge Base' }),
    ).toBeInTheDocument()
  })

  it('falls back to the default title when title is omitted', () => {
    render(<EmptyState description="x" />)

    expect(screen.getByText('No data yet')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd chili_app && npm run test:run -- src/components/ui/__tests__/EmptyState.test.tsx`

Expected: the second test fails because `action` is not a recognized prop on `EmptyState`. TypeScript will also flag the prop as unknown.

- [ ] **Step 3: Add the `action` prop to `EmptyState.tsx`**

Replace the entire contents of `chili_app/src/components/ui/EmptyState.tsx` with:

```tsx
import type { ReactNode } from 'react'

import './ui.css'

type EmptyStateProps = {
  description: string
  title?: string
  action?: ReactNode
}

export function EmptyState({
  action,
  description,
  title = 'No data yet',
}: EmptyStateProps) {
  return (
    <div className="feedback-state feedback-state--empty">
      <div className="feedback-state__title">{title}</div>
      <div>{description}</div>
      {action ? <div className="feedback-state__action">{action}</div> : null}
    </div>
  )
}
```

- [ ] **Step 4: Add CSS rule for the action slot**

In `chili_app/src/components/ui/ui.css`, immediately after the existing `.feedback-state__title { ... }` rule (around line 224-229), append:

```css
.feedback-state__action {
  margin-top: 8px;
  display: flex;
  gap: 10px;
}
```

- [ ] **Step 5: Run all UI tests to verify pass**

Run: `cd chili_app && npm run test:run -- src/components/ui/__tests__/EmptyState.test.tsx`

Expected: all 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add chili_app/src/components/ui/EmptyState.tsx chili_app/src/components/ui/ui.css chili_app/src/components/ui/__tests__/EmptyState.test.tsx
git commit -m "feat(ui): add optional action slot to EmptyState component"
```

---

## Task 2: Wire empty-state CTA on Investigation Workbench

**Files:**
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx` (the no-KB branch around lines 74-91)
- Modify: `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

- [ ] **Step 1: Extend the InvestigationWorkbenchPage test for the CTA**

Append a new `it` block inside the existing `describe('InvestigationWorkbenchPage', ...)` in `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`, after the existing `it('renders a live no-KB state ...')` test:

```tsx
  it('renders a Create Knowledge Base CTA on the no-KB empty state that navigates to /knowledge-bases', async () => {
    render(<InvestigationWorkbenchPage />)

    const cta = await screen.findByRole('button', {
      name: /create knowledge base/i,
    })
    expect(cta).toBeInTheDocument()

    await userEvent.click(cta)

    expect(mocks.navigate).toHaveBeenCalledWith('/knowledge-bases')
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd chili_app && npm run test:run -- src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

Expected: the new test fails — no button with text "Create Knowledge Base" exists yet.

- [ ] **Step 3: Pass an `action` to the no-KB EmptyState**

In `chili_app/src/pages/InvestigationWorkbenchPage.tsx`, replace the existing no-KB branch (the `if (knowledgeBases.length === 0)` block, lines 74-91) with:

```tsx
  if (knowledgeBases.length === 0) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Entity workbench"
          subtitle="Create and ingest a knowledge base before exploring graph entities."
          title="Investigation Workbench"
        />
        <Card>
          <EmptyState
            action={
              <button
                className="page-button"
                onClick={() => navigate('/knowledge-bases')}
                type="button"
              >
                + Create Knowledge Base
              </button>
            }
            description="Investigation queries the graph through a selected knowledge base. Create one, upload documents, and return here to search extracted entities."
            title="No graph-ready knowledge base"
          />
        </Card>
      </section>
    )
  }
```

The `navigate` symbol is already imported from `react-router-dom` and bound at the top of the component (line 35).

- [ ] **Step 4: Re-run the test to verify pass**

Run: `cd chili_app && npm run test:run -- src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

Expected: all tests in the file pass (including the existing "live no-KB state" test and the new CTA test).

- [ ] **Step 5: Commit**

```bash
git add chili_app/src/pages/InvestigationWorkbenchPage.tsx chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx
git commit -m "feat(investigation): add Create KB CTA to empty state"
```

---

## Task 3: Add URL-synced KB picker to RAG Chat

**Files:**
- Modify: `chili_app/src/pages/RagChatPage.tsx`
- Modify: `chili_app/src/pages/__tests__/RagChatPage.test.tsx`

The existing RagChatPage test file uses `globalThis.fetch` mocking and `QueryClientProvider`. The new picker test needs `react-router-dom` (`useSearchParams`, `useNavigate`) mocked at the module level. Switch the test file to the same `vi.hoisted` mock pattern Investigation uses, which is cleaner for these needs.

- [ ] **Step 1: Rewrite the RagChatPage test file with module-level mocks**

Replace the entire contents of `chili_app/src/pages/__tests__/RagChatPage.test.tsx` with:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { RagChatPage } from '../RagChatPage'

const mocks = vi.hoisted(() => ({
  knowledgeBases: [] as Array<{
    id: string
    name: string
    description: string
    status: string
    document_count: number
    entity_count: number
    relationship_count: number
    created_at: string
  }>,
  navigate: vi.fn(),
  setSearchParams: vi.fn(),
  searchParams: new URLSearchParams(),
  createConversation: vi.fn(),
  addMessage: vi.fn(),
  conversation: null as null | {
    id: string
    title: string
    knowledge_base_id: string
    messages: Array<{
      id: string
      role: 'user' | 'assistant'
      content: string
      created_at: string
      citation_ids: string[]
    }>
  },
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => mocks.navigate,
  useSearchParams: () => [mocks.searchParams, mocks.setSearchParams],
}))

vi.mock('../../api/knowledgebases', () => ({
  useKnowledgeBases: () => ({
    isLoading: false,
    isError: false,
    data: { items: mocks.knowledgeBases, total: mocks.knowledgeBases.length },
  }),
}))

vi.mock('../../api/rag', () => ({
  useConversation: () => ({
    isLoading: false,
    isError: false,
    data: mocks.conversation ?? undefined,
  }),
  useCreateConversation: () => ({
    isPending: false,
    mutate: mocks.createConversation,
  }),
  useAddMessage: () => ({
    isPending: false,
    mutate: mocks.addMessage,
  }),
}))

const KB_ONE = {
  id: 'kb-1',
  name: 'Fraud KB',
  description: '',
  status: 'ready',
  document_count: 1,
  entity_count: 2,
  relationship_count: 1,
  created_at: '2026-05-10T00:00:00Z',
}

const KB_TWO = {
  id: 'kb-2',
  name: 'Policy KB',
  description: '',
  status: 'indexing',
  document_count: 0,
  entity_count: 0,
  relationship_count: 0,
  created_at: '2026-05-11T00:00:00Z',
}

describe('RagChatPage', () => {
  beforeEach(() => {
    mocks.knowledgeBases = []
    mocks.navigate.mockReset()
    mocks.setSearchParams.mockReset()
    mocks.searchParams = new URLSearchParams()
    mocks.createConversation.mockReset()
    mocks.addMessage.mockReset()
    mocks.conversation = null
  })

  it('renders a Create Knowledge Base CTA when no KBs exist and navigates on click', async () => {
    render(<RagChatPage />)

    expect(screen.getByText('No knowledge base available')).toBeInTheDocument()

    const cta = screen.getByRole('button', { name: /create knowledge base/i })
    await userEvent.click(cta)

    expect(mocks.navigate).toHaveBeenCalledWith('/knowledge-bases')
  })

  it('renders an option for each KB and defaults to the first one', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-1')
    expect(screen.getByRole('option', { name: /Fraud KB · ready/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /Policy KB · indexing/ })).toBeInTheDocument()
  })

  it('honors the ?kb=... URL parameter when it matches an existing KB', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]
    mocks.searchParams = new URLSearchParams('kb=kb-2')

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-2')
  })

  it('falls back to the first KB when ?kb=... is unknown', () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]
    mocks.searchParams = new URLSearchParams('kb=missing')

    render(<RagChatPage />)

    const select = screen.getByLabelText('Knowledge base') as HTMLSelectElement
    expect(select.value).toBe('kb-1')
  })

  it('updates the URL params when the user picks a different KB', async () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    await userEvent.selectOptions(screen.getByLabelText('Knowledge base'), 'kb-2')

    expect(mocks.setSearchParams).toHaveBeenCalledTimes(1)
    const arg = mocks.setSearchParams.mock.calls[0][0] as URLSearchParams
    expect(arg.get('kb')).toBe('kb-2')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail in the expected ways**

Run: `cd chili_app && npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx`

Expected: tests fail — no `Knowledge base` label exists in `RagChatPage` yet, and the CTA button is missing.

- [ ] **Step 3: Update RagChatPage with URL-synced picker**

Replace the entire contents of `chili_app/src/pages/RagChatPage.tsx` with:

```tsx
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useKnowledgeBases } from '../api/knowledgebases'
import { useAddMessage, useConversation, useCreateConversation } from '../api/rag'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function RagChatPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const knowledgeBasesQuery = useKnowledgeBases()
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const requestedKbId = searchParams.get('kb')
  const selectedKnowledgeBaseId = knowledgeBases.some((kb) => kb.id === requestedKbId)
    ? requestedKbId
    : knowledgeBases[0]?.id ?? null
  const conversationQuery = useConversation(conversationId)
  const createConversationMutation = useCreateConversation()
  const addMessageMutation = useAddMessage(conversationId)

  if (knowledgeBasesQuery.isLoading || (conversationId && conversationQuery.isLoading)) {
    return <LoadingState label="Loading RAG conversation" />
  }

  if (knowledgeBasesQuery.isError) {
    return <ErrorState description="Knowledge base inventory could not be loaded from the backend." />
  }

  if (conversationId && conversationQuery.isError) {
    return <ErrorState description="RAG conversation history could not be loaded from the backend." />
  }

  if (!selectedKnowledgeBaseId) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Conversational RAG"
          subtitle="Create a knowledge base before starting an investigation chat."
          title="RAG Chat"
        />
        <Card>
          <EmptyState
            action={
              <button
                className="page-button"
                onClick={() => navigate('/knowledge-bases')}
                type="button"
              >
                + Create Knowledge Base
              </button>
            }
            description="RAG conversations need at least one knowledge base for retrieval context. Create one and return here to start a thread."
            title="No knowledge base available"
          />
        </Card>
      </section>
    )
  }

  const conversation = conversationQuery.data ?? null

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={conversation?.title ?? 'No active thread'} tone="info" />}
        eyebrow="Conversational RAG"
        subtitle="Conversation creation and message submission now exercise the backend chat endpoints and seeded RAG service."
        title="RAG Chat"
      />

      <Card>
        <div className="metric-stack">
          <div className="metric-row">
            <label className="metric-row__label" htmlFor="rag-kb-select">
              Knowledge base
            </label>
            <select
              className="page-input"
              id="rag-kb-select"
              onChange={(event) => {
                const next = new URLSearchParams(searchParams)
                next.set('kb', event.target.value)
                setSearchParams(next)
                setConversationId(null)
                setDraft('')
              }}
              value={selectedKnowledgeBaseId}
            >
              {knowledgeBases.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name} · {kb.status}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      <div className="page-actions-inline">
        <button
          className="page-button"
          disabled={createConversationMutation.isPending}
          onClick={() =>
            createConversationMutation.mutate(
              {
                knowledge_base_id: selectedKnowledgeBaseId,
                title: `Investigation thread ${new Date().toLocaleTimeString()}`,
              },
              {
                onSuccess: (conversation) => {
                  setConversationId(conversation.id)
                },
              },
            )
          }
          type="button"
        >
          Start new thread
        </button>
      </div>

      <Card>
        {conversation ? (
          <div className="chat-thread">
            {conversation.messages.map((message) => (
              <div
                className={
                  message.role === 'assistant'
                    ? 'chat-bubble chat-bubble--assistant'
                    : 'chat-bubble'
                }
                key={message.id}
              >
                <strong>{message.role}</strong>
                <p>{message.content}</p>
                {message.citation_ids.length > 0 ? (
                  <div className="alert-row-card__meta">
                    {message.citation_ids.map((citationId) => (
                      <Chip key={citationId} label={citationId} tone="default" />
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            description="Start a thread to ask questions against the current knowledge base."
            title="No active conversation"
          />
        )}
      </Card>

      <Card>
        <div className="metric-stack">
          <textarea
            className="page-textarea"
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask the investigation assistant about an entity, alert, or evidence trail"
            value={draft}
          />
          <button
            className="page-button"
            disabled={!conversationId || draft.trim().length === 0 || addMessageMutation.isPending}
            onClick={() => {
              addMessageMutation.mutate({
                content: draft,
                include_graph_context: true,
                filters: {},
              })
              setDraft('')
            }}
            type="button"
          >
            Send message
          </button>
        </div>
      </Card>
    </section>
  )
}
```

Key changes from the original file:
- Added `useNavigate` and `useSearchParams` imports.
- Added `navigate`, `searchParams`, `setSearchParams` locals.
- Replaced `const selectedKnowledgeBaseId = knowledgeBases[0]?.id ?? null` with the URL-aware derivation.
- Added a new picker `<Card>` (between the SectionHeader and the "Start new thread" button) with a labeled `<select>` matching Investigation Workbench's pattern.
- Picker `onChange` calls `setSearchParams`, `setConversationId(null)`, and `setDraft('')`.
- Replaced the no-KB EmptyState with an `action` slot pointing to `/knowledge-bases`.

- [ ] **Step 4: Re-run tests to verify they pass**

Run: `cd chili_app && npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx`

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add chili_app/src/pages/RagChatPage.tsx chili_app/src/pages/__tests__/RagChatPage.test.tsx
git commit -m "feat(rag-chat): add URL-synced KB picker and Create KB empty-state CTA"
```

---

## Task 4: Verify KB switch resets the in-progress draft and conversation

**Files:**
- Modify: `chili_app/src/pages/__tests__/RagChatPage.test.tsx`

The reset behavior is wired in Task 3, but it needs a dedicated test to lock it down.

- [ ] **Step 1: Add a reset-on-switch test**

Append a new `it` block inside the existing `describe('RagChatPage', ...)` block in `chili_app/src/pages/__tests__/RagChatPage.test.tsx` (after the last existing `it` block, just before the closing `})`):

```tsx
  it('clears any in-progress draft when the user switches KB', async () => {
    mocks.knowledgeBases = [KB_ONE, KB_TWO]

    render(<RagChatPage />)

    const textarea = screen.getByPlaceholderText(
      'Ask the investigation assistant about an entity, alert, or evidence trail',
    )
    await userEvent.type(textarea, 'partial question')
    expect((textarea as HTMLTextAreaElement).value).toBe('partial question')

    await userEvent.selectOptions(screen.getByLabelText('Knowledge base'), 'kb-2')

    expect((textarea as HTMLTextAreaElement).value).toBe('')
  })
```

- [ ] **Step 2: Run the test to verify pass**

Run: `cd chili_app && npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx`

Expected: all 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add chili_app/src/pages/__tests__/RagChatPage.test.tsx
git commit -m "test(rag-chat): cover draft reset on KB switch"
```

---

## Task 5: Playwright e2e — Create KB CTA navigation

**Files:**
- Modify: `chili_app/e2e/rag-chat.spec.ts`

The existing e2e file already covers the empty-state visibility. Extend it to verify the CTA click actually lands on `/knowledge-bases`.

- [ ] **Step 1: Read the existing no-KB e2e test**

Open `chili_app/e2e/rag-chat.spec.ts` and locate the test `renders chat interface and shows "no KB" empty state when no knowledge bases exist` (around line 88). The test currently asserts the heading and the empty-state title. Extend it (do NOT add a separate test) so it also clicks the CTA and asserts the URL change.

- [ ] **Step 2: Modify the existing test**

In `chili_app/e2e/rag-chat.spec.ts`, replace the body of the `renders chat interface and shows "no KB" empty state when no knowledge bases exist` test with:

```ts
  test('renders chat interface and shows "no KB" empty state with Create CTA', async ({
    page,
  }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, [])

    await page.goto('/rag-chat')

    await expect(page.getByRole('heading', { name: 'RAG Chat' })).toBeVisible()
    await expect(page.getByText('No knowledge base available')).toBeVisible()

    const cta = page.getByRole('button', { name: /create knowledge base/i })
    await expect(cta).toBeVisible()

    await cta.click()

    await expect(page).toHaveURL(/\/knowledge-bases$/)
  })
```

- [ ] **Step 3: Run the modified e2e test**

Run: `cd chili_app && npm run test:e2e -- rag-chat.spec.ts`

Expected: both tests in `rag-chat.spec.ts` pass. The CTA click must transition to a URL ending in `/knowledge-bases`.

- [ ] **Step 4: Commit**

```bash
git add chili_app/e2e/rag-chat.spec.ts
git commit -m "test(e2e): verify Create KB CTA navigates from RAG Chat empty state"
```

---

## Task 6: Investigation Workbench Playwright e2e — Create KB CTA

**Files:**
- Modify: `chili_app/e2e/investigation-workbench.spec.ts`

The current file has one test (`renders search interface and shows entity results after search`) that mocks `/api/knowledgebases` inline with a populated KB. There is no no-KB test today. Add a new test as a sibling inside the existing `test.describe('Investigation workbench', ...)` block.

- [ ] **Step 1: Update imports**

In `chili_app/e2e/investigation-workbench.spec.ts`, replace the existing import line:

```ts
import { mockAuthenticatedShell } from './helpers/mocks'
```

with:

```ts
import { mockAuthenticatedShell, mockKnowledgeBases } from './helpers/mocks'
```

- [ ] **Step 2: Add the new test inside the describe block**

Add this new `test(...)` block immediately after the closing `})` of the existing `renders search interface and shows entity results after search` test, but before the closing `})` of the surrounding `test.describe('Investigation workbench', ...)`. The new block uses the same indentation as the existing sibling test:

```ts
  test('shows Create KB CTA on the no-KB empty state and navigates on click', async ({
    page,
  }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, [])

    await page.goto('/investigation')

    await expect(page.getByText('No graph-ready knowledge base')).toBeVisible()

    const cta = page.getByRole('button', { name: /create knowledge base/i })
    await expect(cta).toBeVisible()

    await cta.click()

    await expect(page).toHaveURL(/\/knowledge-bases$/)
  })
```

- [ ] **Step 3: Run the e2e tests for this file**

Run: `cd chili_app && npm run test:e2e -- investigation-workbench.spec.ts`

Expected: both tests in the file pass (the existing search test and the new no-KB CTA test).

- [ ] **Step 4: Commit**

```bash
git add chili_app/e2e/investigation-workbench.spec.ts
git commit -m "test(e2e): verify Create KB CTA navigates from Investigation empty state"
```

---

## Task 7: Full verification pass

Run the full local quality gate before declaring complete.

- [ ] **Step 1: Lint**

Run: `cd chili_app && npm run lint`

Expected: no errors, no warnings.

If anything is flagged, fix the underlying issue (do not disable rules or silence warnings) and re-run.

- [ ] **Step 2: TypeScript strict typecheck**

Run: `cd chili_app && npx tsc -b --noEmit`

Expected: no output (clean).

- [ ] **Step 3: Full Vitest suite**

Run: `cd chili_app && npm run test:run`

Expected: all test files pass (including the new `EmptyState` tests and the extended page tests). Note the baseline before this work was 42 files / 186 tests; after this work expect 43 files / ~192 tests.

- [ ] **Step 4: Full Playwright e2e suite**

Run: `cd chili_app && npm run test:e2e`

Expected: all e2e tests pass.

- [ ] **Step 5: Manual browser smoke check**

The dev stack should already be running from earlier in the session (`make dev`). If not, start it from the repo root:

```bash
make dev
```

Then in a browser:

1. Open `http://localhost:5173/investigation`. With zero KBs the page should show "No graph-ready knowledge base" and a `+ Create Knowledge Base` button. Click it — you should land on `/knowledge-bases`.
2. Open `http://localhost:5173/rag-chat` with zero KBs. Same CTA visible. Click it — same destination.
3. Create a KB via the inline form on `/knowledge-bases` (name + description, click Create), upload a small document so the picker has something to compare against.
4. Create a second KB.
5. Open `http://localhost:5173/rag-chat`. The "Knowledge base" picker should be visible with both KBs as options. URL has no `?kb=...` yet.
6. Pick the second KB. URL should update to include `?kb=<id>` and the picker value should change.
7. Click "Start new thread". A thread appears. Type something into the textarea.
8. Switch the picker back to the first KB. The textarea must clear and the thread state must reset to "No active conversation".

- [ ] **Step 6: Final commit if any fixes were made in Step 5**

If the manual smoke check surfaced any issues, fix them and commit:

```bash
git add <files>
git commit -m "fix(rag-chat): <describe fix>"
```

If no fixes were needed, skip this step.

---

## Out of Scope (Tracked, Not Implemented)

- Workspace-level "active KB" indicator in the TopBar — separate future plan.
- Showing `knowledge_base_id` on Alert Feed rows or jumping to Investigation from an alert — would require the alerts API contract to surface `knowledge_base_id`; deferred.
- Conversation history per KB (so switching KB could surface the previous thread for that KB) — currently the local state simply resets; the backend retains conversations and could be exposed via a list endpoint in a future iteration.
- Naming cleanup: `chili_app/src/types/config.ts` and `chili_app/src/types/domainConfig.ts` were noted as dead code during the recent DomainConfig migration — separate cleanup task.

## Success Criteria (from spec)

- From a fresh state with zero KBs, the CTA on either Investigation Workbench or RAG Chat lands the user on `/knowledge-bases` where the inline create form is immediately usable.
- RAG Chat with multiple KBs lets the user pick any KB, persists the choice in the URL (`?kb=...`), and resets `conversationId` + `draft` when the user changes KB.
- Investigation Workbench behavior is unchanged when KBs exist.
- Top-level nav order is unchanged.
- Vitest, ESLint, `tsc -b`, Playwright all green.
