# Sprint 3 Evidence And Contextual RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RAG chat launch from alert, entity, and case workflows with KB/context preselected, evidence-aware prompts, and citation navigation back into the investigation workflow.

**Architecture:** Prefer frontend URL/context handoff over a backend RAG rebuild. Add typed frontend helpers that serialize context into `/rag-chat` query params and `ChatMessageCreateRequest.filters`. Keep backend changes limited to a contract guard unless the existing filters path cannot carry context.

**Tech Stack:** React 19, React Router, TanStack Query, Vite, Vitest, existing FastAPI chat contracts if backend support is required.

**Spec:** [docs/superpowers/specs/2026-06-14-demoable-workflow-increments-design.md](../specs/2026-06-14-demoable-workflow-increments-design.md)

---

## File Structure

- Create: `chili_app/src/lib/ragContext.ts` — context serialization, filters, and citation navigation targets.
- Create: `chili_app/src/lib/__tests__/ragContext.test.ts`
- Modify: `chili_app/src/api/rag.ts` — add start-conversation-with-message helper/hook.
- Modify: `chili_app/src/pages/RagChatPage.tsx` — parse context, prefill prompt, start contextual thread, navigate citations.
- Modify: `chili_app/src/pages/AlertFeedPage.tsx` — add `Ask AI` and URL-backed selected alert.
- Modify: `chili_app/src/pages/CaseManagementPage.tsx` — add case context handoff.
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx` — add entity context handoff.
- Modify: `chili_app/src/components/layout/AiAssistantPanel.tsx` — route current workflow context into RAG or stay disabled without context.
- Modify/create tests under `chili_app/src/pages/__tests__` and `chili_app/src/components/layout/__tests__`.
- Conditional backend only if needed: `backend/api/contracts.py`, `backend/api/dependencies.py`, `backend/api/routers/rag.py`, `backend/tests/api/test_phase5_stateful_routes.py`.

## Task 1: Add Typed RAG Launch Context Helpers

**Files:**
- Create: `chili_app/src/lib/ragContext.ts`
- Create: `chili_app/src/lib/__tests__/ragContext.test.ts`

- [ ] **Step 1: Write failing serialization and navigation tests**

```ts
expect(buildRagChatUrl({
  knowledgeBaseId: 'kb-1',
  source: 'alert',
  alertId: 'alert-1',
  entityId: 'provider-204',
  evidencePackId: 'evidence-1',
  question: DEFAULT_RISK_QUESTION,
})).toBe('/rag-chat?kb=kb-1&source=alert&alert=alert-1&entity=provider-204&evidence=evidence-1&q=Why+is+this+high+risk%3F')

expect(citationNavigationTarget(
  { entity_id: 'provider-204', content_id: 'chunk-1' },
  { knowledgeBaseId: 'kb-1', source: 'alert', alertId: 'alert-1' },
)).toEqual({ pathname: '/investigation/provider-204', search: 'kb=kb-1' })
```

- [ ] **Step 2: Run the failing helper tests**

Run:

```bash
cd chili_app
npm run test:run -- src/lib/__tests__/ragContext.test.ts
```

Expected: FAIL because `ragContext.ts` does not exist.

- [ ] **Step 3: Implement the helper types and constants**

```ts
export type RagLaunchSource = 'alert' | 'entity' | 'case'

export type RagLaunchContext = {
  knowledgeBaseId: string | null
  source: RagLaunchSource | null
  alertId?: string | null
  entityId?: string | null
  caseId?: string | null
  evidencePackId?: string | null
  question?: string | null
}

export const DEFAULT_RISK_QUESTION = 'Why is this high risk?'
```

- [ ] **Step 4: Implement URL serialization/parsing**

Use query keys `kb`, `source`, `alert`, `entity`, `case`, `evidence`, and `q`. Omit empty values.

```ts
export function buildRagChatUrl(context: RagLaunchContext): string {
  const params = new URLSearchParams()
  if (context.knowledgeBaseId) params.set('kb', context.knowledgeBaseId)
  if (context.source) params.set('source', context.source)
  if (context.alertId) params.set('alert', context.alertId)
  if (context.entityId) params.set('entity', context.entityId)
  if (context.caseId) params.set('case', context.caseId)
  if (context.evidencePackId) params.set('evidence', context.evidencePackId)
  if (context.question) params.set('q', context.question)
  const query = params.toString()
  return query ? `/rag-chat?${query}` : '/rag-chat'
}
```

- [ ] **Step 5: Implement filters**

```ts
export function buildRagMessageFilters(context: RagLaunchContext): Record<string, string | number | boolean> {
  return Object.fromEntries(
    [
      ['source_type', context.source],
      ['alert_id', context.alertId],
      ['entity_id', context.entityId],
      ['case_id', context.caseId],
      ['evidence_pack_id', context.evidencePackId],
    ].filter((entry): entry is [string, string] => typeof entry[1] === 'string' && entry[1].length > 0),
  )
}
```

- [ ] **Step 6: Implement citation navigation targets**

Navigation rules:

- `citation.entity_id` -> `/investigation/{entity_id}?kb={knowledgeBaseId}`
- Source alert context -> `/alerts?alert={alertId}`
- Source case context -> `/cases?kb={knowledgeBaseId}&case={caseId}`
- Otherwise return `null`.

- [ ] **Step 7: Run helper tests**

Run:

```bash
cd chili_app
npm run test:run -- src/lib/__tests__/ragContext.test.ts
```

Expected: tests pass.

## Task 2: Add Contextual Launch Actions To Workflow Pages

**Files:**
- Modify: `chili_app/src/pages/AlertFeedPage.tsx`
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Modify: `chili_app/src/pages/InvestigationWorkbenchPage.tsx`
- Modify: `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx`
- Modify: `chili_app/src/pages/__tests__/CaseManagementPage.test.tsx`
- Modify: `chili_app/src/pages/__tests__/InvestigationWorkbenchPage.test.tsx`

- [ ] **Step 1: Add failing navigation tests**

Alert Feed:

```ts
await userEvent.click(screen.getByRole('button', { name: /ask ai/i }))
expect(navigateMock).toHaveBeenCalledWith('/rag-chat?kb=kb-1&source=alert&alert=alert-1&entity=provider-204&evidence=evidence-1&q=Why+is+this+high+risk%3F')
```

Case Management:

```ts
await userEvent.click(screen.getByRole('button', { name: /ask ai/i }))
expect(navigateMock).toHaveBeenCalledWith(expect.stringContaining('source=case'))
expect(navigateMock).toHaveBeenCalledWith(expect.stringContaining('case=case-1'))
```

Investigation:

```ts
await userEvent.click(screen.getByRole('button', { name: /ask ai/i }))
expect(navigateMock).toHaveBeenCalledWith(expect.stringContaining('source=entity'))
expect(navigateMock).toHaveBeenCalledWith(expect.stringContaining('entity=provider-204'))
```

- [ ] **Step 2: Run failing page tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx
```

Expected: tests fail because `Ask AI` actions are absent.

- [ ] **Step 3: Update Alert Feed**

Use URL-backed `alert` search param for selected evidence where possible. Add an `Ask AI` row button using:

```tsx
navigate(buildRagChatUrl({
  knowledgeBaseId: alert.knowledge_base_id,
  source: 'alert',
  alertId: alert.id,
  entityId: alert.entity_id,
  evidencePackId: alert.evidence_pack_id,
  question: DEFAULT_RISK_QUESTION,
}))
```

- [ ] **Step 4: Update Case Management**

Read `case` from search params as the selected case when valid. Add `Ask AI` in case detail:

```tsx
navigate(buildRagChatUrl({
  knowledgeBaseId,
  source: 'case',
  caseId: activeCaseId,
  alertId: caseQuery.data.case.alert_ids[0],
  evidencePackId: caseQuery.data.case.evidence_pack_id,
  question: DEFAULT_RISK_QUESTION,
}))
```

- [ ] **Step 5: Update Investigation Workbench**

Add `Ask AI` near the selected entity/risk section:

```tsx
navigate(buildRagChatUrl({
  knowledgeBaseId: activeKnowledgeBaseId,
  source: 'entity',
  entityId: selectedEntityId,
  alertId: selectedAlert?.id,
  evidencePackId: selectedAlert?.evidence_pack_id,
  question: DEFAULT_RISK_QUESTION,
}))
```

- [ ] **Step 6: Run page tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx
```

Expected: contextual launch tests pass.

## Task 3: Make RAG Chat Consume Context And Start Contextual Threads

**Files:**
- Modify: `chili_app/src/api/rag.ts`
- Modify: `chili_app/src/pages/RagChatPage.tsx`
- Modify: `chili_app/src/pages/__tests__/RagChatPage.test.tsx`

- [ ] **Step 1: Add failing RAG page tests**

```ts
render(<MemoryRouter initialEntries={['/rag-chat?kb=kb-1&source=alert&alert=alert-1&entity=provider-204&evidence=evidence-1&q=Why+is+this+high+risk%3F']}><RagChatPage /></MemoryRouter>)

expect(await screen.findByLabelText('Knowledge base')).toHaveValue('kb-1')
expect(screen.getByDisplayValue('Why is this high risk?')).toBeInTheDocument()

await userEvent.click(screen.getByRole('button', { name: /start contextual thread/i }))
expect(mocks.startConversationWithMessage).toHaveBeenCalledWith(expect.objectContaining({
  content: 'Why is this high risk?',
  filters: expect.objectContaining({
    source_type: 'alert',
    alert_id: 'alert-1',
    entity_id: 'provider-204',
    evidence_pack_id: 'evidence-1',
  }),
}))
```

- [ ] **Step 2: Run failing RAG tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx
```

Expected: tests fail because contextual thread start is absent.

- [ ] **Step 3: Add `startConversationWithMessage` API helper**

```ts
export async function startConversationWithMessage(payload: {
  knowledge_base_id: string
  title: string
  content: string
  filters: Record<string, string | number | boolean>
}): Promise<ConversationResponse> {
  const created = await createConversation({
    knowledge_base_id: payload.knowledge_base_id,
    title: payload.title,
  })
  return addMessage(created.id, {
    content: payload.content,
    include_graph_context: true,
    filters: payload.filters,
  })
}
```

Add `useStartConversationWithMessage()` with query invalidation for `conversationQueryKey(updated.id)`.

- [ ] **Step 4: Parse and render launch context in `RagChatPage.tsx`**

Parse `searchParams` with `parseRagLaunchContext`, prefer `context.knowledgeBaseId` over default KB, prefill draft from `q`, and render chips for source, alert/entity/case/evidence IDs.

- [ ] **Step 5: Add the contextual start button**

Render `Start contextual thread` when there is no active conversation and a context question is present. On click, call the new hook with title:

- `Alert investigation`
- `Case investigation`
- `Entity investigation`

- [ ] **Step 6: Preserve existing manual chat**

Keep `New thread` and `Send` behavior working for non-contextual chat.

- [ ] **Step 7: Run RAG tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx
```

Expected: contextual and manual chat tests pass.

## Task 4: Add Citation Navigation In Chat

**Files:**
- Modify: `chili_app/src/pages/RagChatPage.tsx`
- Modify: `chili_app/src/pages/__tests__/RagChatPage.test.tsx`

- [ ] **Step 1: Add failing citation navigation tests**

```ts
expect(screen.getByRole('link', { name: /open citation context/i })).toHaveAttribute(
  'href',
  '/investigation/provider-204?kb=kb-1',
)
```

Also test fallback routes:

- Alert fallback -> `/alerts?alert=alert-1`
- Case fallback -> `/cases?kb=kb-1&case=case-1`
- No target -> non-clickable citation card.

- [ ] **Step 2: Render citation links only when a target exists**

Use `citationNavigationTarget(citation, context)` for each citation. Preserve document/record id, score, snippet, content id, and chunk index display.

- [ ] **Step 3: Run RAG citation tests**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/RagChatPage.test.tsx
```

Expected: citation navigation tests pass.

## Task 5: Wire The Global AI Assistant Panel Into Contextual RAG

**Files:**
- Modify: `chili_app/src/components/layout/AiAssistantPanel.tsx`
- Create/modify: `chili_app/src/components/layout/__tests__/AiAssistantPanel.test.tsx`

- [ ] **Step 1: Add failing assistant panel tests**

```tsx
render(
  <MemoryRouter initialEntries={['/investigation/provider-204?kb=kb-1']}>
    <AiAssistantPanel />
  </MemoryRouter>,
)
await userEvent.type(screen.getByLabelText('Ask the AI investigator'), 'Why is this high risk?')
await userEvent.click(screen.getByRole('button', { name: /send message/i }))

expect(navigateMock).toHaveBeenCalledWith('/rag-chat?kb=kb-1&source=entity&entity=provider-204&q=Why+is+this+high+risk%3F')
```

Also assert send is disabled on `/dashboard`.

- [ ] **Step 2: Parse route context in `AiAssistantPanel.tsx`**

Use `useLocation` and `useNavigate`. Supported context:

- `/alerts?kb=...&alert=...` -> alert context
- `/cases?kb=...&case=...` -> case context
- `/investigation/:entityId?kb=...` -> entity context
- `/rag-chat?...` -> current RAG context

- [ ] **Step 3: Replace the static assistant panel body**

If context exists, show concise context summary and enable composer. If no context exists, show:

```tsx
Open an alert, case, or entity to attach context.
```

Disable send without context or without a draft.

- [ ] **Step 4: Navigate to contextual RAG on send**

```tsx
navigate(buildRagChatUrl({ ...context, question: draft.trim() }))
```

- [ ] **Step 5: Run assistant panel tests**

Run:

```bash
cd chili_app
npm run test:run -- src/components/layout/__tests__/AiAssistantPanel.test.tsx
```

Expected: tests pass.

## Task 6: Backend Contract Guard

**Files:**
- Review: `backend/api/contracts.py`
- Review: `backend/api/dependencies.py`
- Review: `backend/api/routers/rag.py`
- Conditional modify only if needed.

- [ ] **Step 1: Confirm existing backend support**

Verify:

- `ChatMessageCreateRequest.filters` accepts scalar dictionaries.
- Chat payload construction passes `payload.filters` into `RagQueryRequest`.
- `ChatCitationResponse` includes enough fields for UI display and navigation.

- [ ] **Step 2: Avoid backend changes if filters already support context**

If the checks pass, do not change backend code.

- [ ] **Step 3: Make a narrow backend change only if required**

If a top-level field is required, add:

```python
launch_context: dict[str, str | int | float | bool] = Field(default_factory=dict)
```

to `ChatMessageCreateRequest`, merge it into filters before constructing the RAG query, and add backend tests proving the merged context reaches RAG filters.

- [ ] **Step 4: Regenerate contracts if backend changed**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
```

Expected: generated schema is updated only if backend contracts changed.

## Task 7: Final Verification

**Files:**
- All touched frontend/backend files.

- [ ] **Step 1: Run focused frontend tests**

Run:

```bash
cd chili_app
npm run test:run -- src/lib/__tests__/ragContext.test.ts src/pages/__tests__/RagChatPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/components/layout/__tests__/AiAssistantPanel.test.tsx
```

Expected: all focused tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```bash
cd chili_app
npm run build
```

Expected: typecheck/build passes.

- [ ] **Step 3: Run backend gates only if backend changed**

Run:

```bash
uv run --project backend pyright
uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py -q
```

Expected: backend checks pass if backend was touched.

## Acceptance Checks

- [ ] Alert Feed `Ask AI` opens RAG Chat with KB, alert, entity, evidence, and `Why is this high risk?`.
- [ ] Case Management `Ask AI` preserves case and KB context.
- [ ] Investigation Workbench `Ask AI` preserves entity and KB context.
- [ ] `Start contextual thread` sends `include_graph_context: true` and filters containing source IDs.
- [ ] Assistant answers still render citations.
- [ ] Citation with entity context navigates to `/investigation/:entityId?kb=...`.
- [ ] Citation fallback opens alert or case context when entity context is absent.
- [ ] Global AI panel opens contextual RAG from alert, case, or entity routes and stays disabled on dashboard.

## Demo Script

1. Open `/alerts`.
2. Click `Ask AI` on a high-risk alert.
3. Confirm `/rag-chat` opens with KB, alert, entity, evidence, and default question prefilled.
4. Click `Start contextual thread`.
5. Confirm the answer renders citations.
6. Click an entity citation and confirm Investigation opens with the same KB.
7. Open a case and click `Ask AI`.
8. Confirm RAG Chat opens with case context.
9. Open an entity route and use the global AI panel to submit a question.
