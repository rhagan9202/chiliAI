# Contextual Knowledge Base Entry Points

## Goal

Surface knowledge base (KB) selection and creation at the moments where analysts need them, rather than promoting Knowledge Bases higher in the top-level navigation. Investigation Workbench and RAG Chat both depend on a selected KB but currently dead-end when none exist, and RAG Chat has no real picker at all. This work closes those gaps without changing the existing nav order.

## Current Context

Three pages are affected today:

- `chili_app/src/pages/InvestigationWorkbenchPage.tsx` — already has a labeled `<select>` row for picking a KB, persisted to the URL via `?kb=...`. When zero KBs exist, the page renders a text-only `EmptyState` telling the user to "Create one on the Knowledge Bases page" but provides no button or link to actually navigate there.
- `chili_app/src/pages/RagChatPage.tsx` — hardcodes the active KB to `knowledgeBases[0]?.id ?? null`. There is no picker. When zero KBs exist, the page renders the same text-only dead-end empty state.
- `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` (route `/knowledge-bases`) — full CRUD page; landing on it shows the create form inline, so a plain navigation is sufficient (no `?new=1` flag or modal needed).

The shared `EmptyState` component (`chili_app/src/components/ui/EmptyState.tsx`) accepts only `{title, description}` and has no slot for actions. It is used throughout the app, so any change must be backwards-compatible.

The KB selector pattern Investigation already uses — a labeled `<select>` row inside a `<Card>` with a `metric-row__label` — is the convention we will standardize on for KB pickers across the app.

## Scope

This is a focused medium-scope change. Out of scope (deferred):

- Promoting Knowledge Bases higher in the top-level navigation.
- Adding a workspace-level "active KB" indicator in the TopBar.
- Showing KB context on Alert Feed rows or adding "Open in Investigation" actions to alerts (this would require alerts to expose `knowledge_base_id` on the API contract — a separate change).
- A "Learn about KBs" secondary link or any in-app KB documentation route.

## Design

### 1. Extend `EmptyState` with an optional action slot

Add a single optional prop. Existing call sites are unchanged.

```ts
type EmptyStateProps = {
  description: string
  title?: string
  action?: ReactNode
}
```

The action renders below the description with a small top margin. Styling lives in `chili_app/src/components/ui/ui.css` under a new `.feedback-state__action` rule.

### 2. Investigation Workbench — actionable empty state

When `knowledgeBases.length === 0`, the no-KB branch in `InvestigationWorkbenchPage.tsx` already returns an `EmptyState`. Pass `action` with a primary button that uses `react-router-dom`'s `useNavigate` to go to `/knowledge-bases`:

```tsx
<EmptyState
  title="No graph-ready knowledge base"
  description="Investigation queries the graph through a selected knowledge base. Create one, upload documents, and return here to search extracted entities."
  action={
    <button
      className="page-button"
      onClick={() => navigate('/knowledge-bases')}
      type="button"
    >
      + Create Knowledge Base
    </button>
  }
/>
```

The mid-page KB picker (when KBs do exist) is left as-is — it already matches the chosen pattern.

### 3. RAG Chat — actionable empty state + real KB picker

`RagChatPage.tsx` requires three changes:

**a. URL-synced KB selection.** Replace the line `const selectedKnowledgeBaseId = knowledgeBases[0]?.id ?? null` with a URL-parameter-driven selection that mirrors Investigation's behavior:

```tsx
const [searchParams, setSearchParams] = useSearchParams()
const requestedKbId = searchParams.get('kb')
const selectedKnowledgeBaseId = knowledgeBases.some((kb) => kb.id === requestedKbId)
  ? requestedKbId
  : knowledgeBases[0]?.id ?? null
```

This makes the active KB shareable via URL and consistent with Investigation.

**b. Labeled-row picker inside a `<Card>`.** Add a new card above the conversation card containing the picker, modeled on Investigation's `metric-row` shape:

```tsx
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
          setConversationId(null)  // reset thread on KB change
        }}
        value={selectedKnowledgeBaseId ?? ''}
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
```

**c. Conversation reset on KB change.** When the picker value changes, set `conversationId` back to `null` and clear the in-progress `draft` textarea. Conversations are anchored to a specific KB on the backend; resetting the local state is less surprising than silently submitting messages against a different KB. The previous thread continues to exist on the backend and can be re-opened later if conversation history features are added.

**d. Actionable empty state.** The no-KB branch already renders a `<SectionHeader>` plus a `<Card>` wrapping an `EmptyState`. Keep that structure and add the `action` prop to the existing `EmptyState` call:

```tsx
<EmptyState
  title="No knowledge base available"
  description="RAG conversations need at least one knowledge base for retrieval context. Create one and return here to start a thread."
  action={
    <button
      className="page-button"
      onClick={() => navigate('/knowledge-bases')}
      type="button"
    >
      + Create Knowledge Base
    </button>
  }
/>
```

### 4. Testing

- `chili_app/src/components/ui/__tests__/EmptyState.test.tsx` — new file. Verify the component renders title + description without `action`, and renders the action node when supplied. Verify no extra DOM elements appear when `action` is omitted.
- `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx` — extend existing tests. Mock `useKnowledgeBases` to return zero items; assert the "Create Knowledge Base" button is present and that clicking it navigates to `/knowledge-bases`.
- `chili_app/src/pages/__tests__/RagChatPage.test.tsx` — extend existing tests. Cover (1) the new picker rendering options for each KB, (2) URL parameter sync when the picker changes, (3) `conversationId` reset when the picker changes mid-thread, (4) the empty-state CTA navigates to `/knowledge-bases`.
- All Vitest tests, ESLint, and `tsc -b` must remain clean. No new pyright surface (frontend-only change).

### 5. Files touched

| File | Change |
|------|--------|
| `chili_app/src/components/ui/EmptyState.tsx` | Add optional `action?: ReactNode` prop |
| `chili_app/src/components/ui/ui.css` | Add `.feedback-state__action` rule (top margin only) |
| `chili_app/src/pages/InvestigationWorkbenchPage.tsx` | Pass `action` to the no-KB `EmptyState` |
| `chili_app/src/pages/RagChatPage.tsx` | Add URL-synced picker, conversation reset on switch, action on empty state |
| `chili_app/src/components/ui/__tests__/EmptyState.test.tsx` | New test file |
| `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx` | Extend to cover empty-state CTA |
| `chili_app/src/pages/__tests__/RagChatPage.test.tsx` | Extend to cover picker, URL sync, conversation reset, empty-state CTA |

## Success Criteria

- From a fresh state with zero KBs, clicking the "Create Knowledge Base" CTA on either Investigation Workbench or RAG Chat navigates to `/knowledge-bases` where the user can immediately create one via the existing inline form.
- RAG Chat with multiple KBs lets the user pick any KB, persists the choice in the URL (`?kb=...`), and resets any in-progress conversation thread when the user changes KB.
- Investigation Workbench behavior is unchanged when KBs exist; only the no-KB empty state changes.
- Top-level nav order is unchanged.
- Existing call sites of `EmptyState` render identically (no visual regression).
- Vitest, ESLint, `tsc -b` all green. Playwright e2e: a new short flow that loads `/rag-chat` with zero KBs, clicks the CTA, lands on `/knowledge-bases`.
