# SAFE-CMS-007 Citation-First Navigable Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make evidence and RAG citations resolve to deterministic, KB-scoped UI destinations or explicit unsupported states.

**Architecture:** Add a shared frontend citation target resolver that accepts normalized evidence provenance and RAG citation shapes, then use it from evidence panels and RAG chat. Keep route resolution contract-driven and conservative: only supported source types become links, and legacy or unsafe targets render inert with a reason.

**Tech Stack:** React, TypeScript, React Router, Vitest, Playwright, existing FastAPI/OpenAPI contracts.

---

## Current Inventory

- `chili_app/src/components/investigation/EvidencePackViewer.tsx` renders provenance references from `EvidencePackResponse.provenance`, but `route_target` is displayed as inert text.
- `chili_app/src/lib/ragContext.ts` builds RAG launch URLs and has `citationNavigationTarget`, which currently knows only RAG citation entity/context fallbacks.
- `chili_app/src/pages/RagChatPage.tsx` renders RAG citations as links only when `citationNavigationTarget` returns a target.
- The backend already exposes document preview routes at `/knowledgebases/{knowledge_base_id}/documents/{document_id}/preview`, policy item routes through `/policy/items/{item_id}?knowledge_base_id=...`, workflow routes through `/workflows/{workflow_id}`, investigation routes through `/investigation/:entityId?kb=...`, and alert/case routes through `/alerts?alert=...` and `/cases?kb=...&case=...`.
- SAFE-CMS-004 provenance generation writes reference types such as `document`, `graph_node`, `graph_edge`, `risk_score`, `feature_attribution`, `narrative_section`, `correlation_id`, `workflow_run`, `model_version`, and `prompt_version`.

## Task 1: Shared Citation Target Resolver

**Files:**
- Create: `chili_app/src/lib/citationTargets.ts`
- Test: `chili_app/src/lib/__tests__/citationTargets.test.ts`
- Modify: `docs/superpowers/plans/2026-08-03-safe-cms-007-citation-navigation.md`

- [x] **Step 1: Write failing resolver tests**

Create `chili_app/src/lib/__tests__/citationTargets.test.ts` with tests for:

```ts
resolveEvidenceCitationTarget({
  knowledgeBaseId: 'kb-1',
  reference: {
    reference_type: 'document',
    reference_id: 'doc-1#evidence:0',
    label: 'Claim note',
    route_target: '/knowledgebases/kb-1/documents/doc-1/preview',
    metadata: {},
  },
})
```

Expected unsupported result until the KB document page consumes `document` selection:

```ts
{
  kind: 'unsupported',
  label: 'Claim note',
  sourceType: 'document',
  reason: 'Document preview selection is not routable yet.',
}
```

Also test backend entity route normalization from `/investigation/entities/provider-1?knowledge_base_id=kb-1` to `/investigation/provider-1?kb=kb-1`, derived model/prompt references returning `kind: 'unsupported'`, current backend `workflow` and `correlation` references returning `kind: 'unsupported'`, document/policy/workflow refs staying inert until their destination pages consume selection params, legacy refs without KB scope returning `kind: 'unsupported'`, mismatched KB route targets returning `kind: 'unsupported'`, protocol-relative URLs returning `kind: 'unsupported'`, and encoded traversal route targets returning `kind: 'unsupported'`.

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
cd chili_app
pnpm exec vitest run src/lib/__tests__/citationTargets.test.ts
```

Expected: fail because `../citationTargets` does not exist.

- [x] **Step 3: Implement the minimal resolver**

Create `chili_app/src/lib/citationTargets.ts` exporting:

```ts
type CitationLinkTarget = {
  kind: 'link'
  label: string
  sourceType: string
  to: string
  preview: string
}

type UnsupportedCitationTarget = {
  kind: 'unsupported'
  label: string
  sourceType: string
  reason: string
}

export type CitationTarget = CitationLinkTarget | UnsupportedCitationTarget
```

Add `resolveEvidenceCitationTarget`, `resolveRagCitationTarget`, route-target parsing helpers, KB-scope checks, `encodeURIComponent` for path pieces, and URLSearchParams for query strings.

- [x] **Step 4: Run tests to verify GREEN**

Run:

```bash
cd chili_app
pnpm exec vitest run src/lib/__tests__/citationTargets.test.ts
```

Expected: all resolver tests pass.

- [x] **Step 5: Commit Task 1**

Run focused lint and commit only Task 1 files:

```bash
cd chili_app
pnpm exec eslint src/lib/citationTargets.ts src/lib/__tests__/citationTargets.test.ts
cd ..
git diff --check
git add docs/superpowers/plans/2026-08-03-safe-cms-007-citation-navigation.md chili_app/src/lib/citationTargets.ts chili_app/src/lib/__tests__/citationTargets.test.ts
git commit -m "Add SAFE-CMS-007 citation target resolver"
```

Task 1 notes:

- Added `chili_app/src/lib/citationTargets.ts` with deterministic resolver results for
  document, graph/entity, policy item, workflow, derived model/prompt, legacy no-KB,
  unsupported, and unsafe route-target states.
- Red verification first failed on missing `../citationTargets` after fixing test syntax.
- Sidecar review found that document, policy item, and workflow URLs would be broken
  if marked supported before destination pages consume `document`, `item`, or `workflow`
  query params. Tightened Task 1 so only current routable investigation targets become
  links; unconsumed destination selections stay unsupported with explicit reasons.
- Green verification passed:
  - `pnpm exec vitest run src/lib/__tests__/citationTargets.test.ts`: 12 passed.
- Focused lint and whitespace verification passed:
  - `pnpm exec eslint src/lib/citationTargets.ts src/lib/__tests__/citationTargets.test.ts`: passed.
  - `git diff --check`: passed.

## Task 2: Evidence Provenance Click-Through

**Files:**
- Modify: `chili_app/src/components/investigation/EvidencePackViewer.tsx`
- Test: `chili_app/src/components/investigation/__tests__/EvidencePackViewer.test.tsx`
- Modify: `chili_app/src/pages/pages.css`
- Modify: `docs/superpowers/plans/2026-08-03-safe-cms-007-citation-navigation.md`

- [x] **Step 1: Write failing evidence viewer tests**

Extend `EvidencePackViewer.test.tsx` so resolver-supported entity/graph provenance renders as links with source-type text, while document, policy-item, workflow, model/prompt, correlation, and legacy references render as non-clickable rows with reason text until their destination pages consume exact selection params.

- [x] **Step 2: Run tests to verify RED**

Run:

```bash
cd chili_app
pnpm exec vitest run src/components/investigation/__tests__/EvidencePackViewer.test.tsx
```

Expected: fail because provenance rows do not link through the resolver.

- [x] **Step 3: Wire `EvidencePackViewer` to the resolver**

Pass `knowledgeBaseId` into the viewer from callers that have it. Render supported provenance as compact React Router links with source labels and preview text. Render unsupported references as disabled text with the resolver reason.

- [x] **Step 4: Run tests to verify GREEN**

Run:

```bash
cd chili_app
pnpm exec vitest run src/components/investigation/__tests__/EvidencePackViewer.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx
```

Expected: evidence viewer and calling page tests pass.

- [x] **Step 5: Commit Task 2**

Run focused lint/build and commit only Task 2 files.

Task 2 notes:

- Added `knowledgeBaseId` to `EvidencePackViewer` and threaded the selected KB from
  Alert Feed and Investigation Workbench.
- Evidence provenance now renders resolver-supported entity/investigation references
  as React Router links and all unsupported references with explicit reason text.
- Kept document/policy/workflow route targets non-clickable until destination pages
  consume exact selection params, matching the Task 1 review finding.
- Red verification failed on the missing `Open citation source Provider risk profile`
  link.
- Green verification passed:
  - `pnpm exec vitest run src/components/investigation/__tests__/EvidencePackViewer.test.tsx`: 6 passed.
  - `pnpm exec vitest run src/components/investigation/__tests__/EvidencePackViewer.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx`: 81 passed.
- Final Task 2 verification passed:
  - `pnpm exec eslint src/lib/citationTargets.ts src/lib/__tests__/citationTargets.test.ts src/components/investigation/EvidencePackViewer.tsx src/components/investigation/__tests__/EvidencePackViewer.test.tsx src/pages/InvestigationWorkbenchPage.tsx src/pages/AlertFeedPage.tsx`: passed.
  - `pnpm build`: passed with the existing Vite large-chunk warning.
  - `backend/.venv/bin/python scripts/backlog_consistency.py --check`: passed.
  - `git diff --check`: passed.

## Task 3: RAG Citation Resolver Unification

**Files:**
- Modify: `chili_app/src/lib/ragContext.ts`
- Modify: `chili_app/src/pages/RagChatPage.tsx`
- Test: `chili_app/src/lib/__tests__/ragContext.test.ts`
- Test: `chili_app/src/pages/__tests__/RagChatPage.test.tsx`
- Modify: `docs/superpowers/plans/2026-08-03-safe-cms-007-citation-navigation.md`

- [ ] **Step 1: Write failing RAG navigation tests**

Add tests proving document/chunk RAG citations resolve to the document preview surface with KB scope, entity citations preserve alert/case/evidence context, and unsupported citations remain inert.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd chili_app
pnpm exec vitest run src/lib/__tests__/ragContext.test.ts src/pages/__tests__/RagChatPage.test.tsx
```

Expected: fail on missing document citation target behavior.

- [ ] **Step 3: Reuse the shared resolver**

Update `citationNavigationTarget` or replace it with `resolveRagCitationTarget` so RAG links share the same source-type support matrix and KB-scope rules as evidence provenance.

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
cd chili_app
pnpm exec vitest run src/lib/__tests__/citationTargets.test.ts src/lib/__tests__/ragContext.test.ts src/pages/__tests__/RagChatPage.test.tsx
```

Expected: citation resolver and RAG tests pass.

- [ ] **Step 5: Commit Task 3**

Run focused lint/build and commit only Task 3 files.

## Task 4: Browser Click-Through Verification

**Files:**
- Modify/create: `chili_app/e2e/citation-navigation.spec.ts`
- Modify: `docs/superpowers/plans/2026-08-03-safe-cms-007-citation-navigation.md`

- [ ] **Step 1: Write failing Playwright coverage**

Create a full-stack test that seeds an alert/evidence pack with document provenance, opens the cockpit evidence panel, clicks the citation, and verifies the document preview panel opens with the selected KB and document.

- [ ] **Step 2: Run test to verify RED**

Bring up the dev stack if needed, then run:

```bash
cd chili_app
pnpm exec playwright test e2e/citation-navigation.spec.ts
```

Expected: fail until evidence provenance renders as a supported link.

- [ ] **Step 3: Harden UI route handling**

Add only the route/query handling needed for the browser test. Do not introduce a new backend resolver endpoint unless the frontend contract cannot safely build the target.

- [ ] **Step 4: Run full focused verification**

Run:

```bash
cd chili_app
pnpm exec vitest run src/lib/__tests__/citationTargets.test.ts src/lib/__tests__/ragContext.test.ts src/components/investigation/__tests__/EvidencePackViewer.test.tsx src/pages/__tests__/RagChatPage.test.tsx src/pages/__tests__/InvestigationWorkbenchPage.test.tsx src/pages/__tests__/AlertFeedPage.test.tsx
pnpm exec eslint src/lib/citationTargets.ts src/lib/ragContext.ts src/pages/RagChatPage.tsx src/components/investigation/EvidencePackViewer.tsx src/lib/__tests__/citationTargets.test.ts src/lib/__tests__/ragContext.test.ts src/pages/__tests__/RagChatPage.test.tsx src/components/investigation/__tests__/EvidencePackViewer.test.tsx
pnpm build
pnpm exec playwright test e2e/citation-navigation.spec.ts
cd ..
backend/.venv/bin/python scripts/backlog_consistency.py --check
git diff --check
```

Expected: all focused checks pass; any known Vite large-chunk warning is unchanged.

- [ ] **Step 5: Final commit and push**

Update backlog status if the whole story is complete, commit the final slice, and push `fix/normalize-kb-query-param`.

## Review Gates

- Review after Task 1 before wiring the resolver into UI surfaces.
- Review after Task 3 before starting browser click-through coverage.
- Final review before backlog status changes and push.

## Definition Of Done

- Every supported evidence provenance type renders deterministically as a link or an unsupported state.
- Unsupported and legacy refs never become broken links.
- Document, graph/entity, policy item, workflow, alert, case, and RAG citation targets preserve KB scope.
- RAG launches continue to use shallow scalar filters accepted by the backend contract.
- Focused unit/component tests, lint, build, browser click-through, backlog consistency, and whitespace checks pass.
