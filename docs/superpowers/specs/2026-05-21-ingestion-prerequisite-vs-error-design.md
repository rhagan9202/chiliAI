# Ingestion Studio Prerequisite vs. Validation Error Separation

## Goal

Fix the cold-load Ingestion Studio (`/knowledge-bases`) so the Validate step in the wizard no longer renders in a red "Needs attention" state before the user has done anything. Required-state issues (no knowledge base selected, no source type chosen, no feed selected) should be treated as **prerequisites the user has yet to satisfy**, not as **validation errors against state they have entered**. Real content validation failures (bad files, malformed CSV rows, backend rejection responses) continue to surface as errors normally.

## Current Context

`chili_app/src/pages/KnowledgeBaseManagerPage.tsx` renders the Ingestion Studio. On every render it computes:

```ts
const requiredIssues = validateRequiredWizardState({
  knowledgeBaseId: activeKnowledgeBaseId,
  sourceType: studio.sourceType,
  feedName: studio.selectedFeedName,
})
const currentIssues = [
  ...requiredIssues,
  ...(studio.sourceType === 'documents' ? documentIssues : []),
  ...(studio.sourceType === 'records' ? recordIssues : []),
  ...studio.validationIssues,
]

const completedStepIds = new Set([
  ...(activeKnowledgeBaseId ? (['knowledge-base'] as const) : []),
  ...(studio.sourceType ? (['source'] as const) : []),
  ...(studio.pendingFiles.length > 0 || studio.parsedRows.length > 0 ? (['preview'] as const) : []),
  ...(currentIssues.length === 0 ? (['validate'] as const) : []),
  ...(studio.receipts.length > 0 ? (['submit'] as const) : []),
])
const errorStepIds = new Set(currentIssues.length > 0 ? (['validate'] as const) : [])
```

On cold load `requiredIssues` contains two entries (`missing-kb`, `missing-source`), so `currentIssues.length > 0`, so `errorStepIds` contains `'validate'`. The `IngestionStepper` component then renders the Validate step with a `CircleAlert` icon and a red "Needs attention" `Chip`. This reads as the app being broken before the user has interacted at all.

`ValidationPanel` (`chili_app/src/components/ingestion/ValidationPanel.tsx`) takes the same `currentIssues` list and renders all issues grouped by `source` (`'client'` / `'backend'`), with a count chip toned `danger` when any issue is `severity: 'error'`. So the panel also reports "Client check / 2 ISSUES" on cold load with two red error rows.

The submit guards in `submitDocuments()` and `submitRecords()` re-call `validateRequiredWizardState` directly and block submission when any issue has `severity: 'error'`. They are the authoritative gate on submission; the display state in the stepper and panel is purely visual.

## Scope

In scope:
- Distinguishing prerequisite issues from content validation issues at the data-model level.
- Updating the wizard stepper so the Validate step only flips to "error" or "complete" based on real content validation results.
- Updating the ValidationPanel so prerequisites render as soft "to do" guidance rather than red errors.
- Test coverage for the new behaviour on cold load, after partial progress, and on real validation failures.

Out of scope:
- Click-through navigation on the stepper (still display-only).
- Resetting the Zustand store on route entry.
- Delete-KB confirmation dialog.
- Source-type card CSS truncation.
- Backend changes — this is a pure frontend display fix.

## Design

### 1. Type addition — `ValidationKind` discriminator

In `chili_app/src/lib/ingestion/types.ts`, add a new type union and an optional field on `ValidationIssue`:

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

`kind` is optional. Call sites that omit it (today: every backend-derived issue constructed in `submitDocuments`/`submitRecords` and `validateDocumentFiles`/`validateRecordFile`/`validateRecordRows`) are treated as `'content'` by consumers. This keeps the change backwards-compatible without a flag-day rewrite.

### 2. Producer change — `validateRequiredWizardState`

In `chili_app/src/lib/ingestion/validateIngestion.ts`, the three issues emitted by `validateRequiredWizardState` (ids `missing-kb`, `missing-source`, `missing-feed`) gain `kind: 'prerequisite'`. The internal `issue()` helper stays the same; the prerequisite kind is applied at the `validateRequiredWizardState` call sites:

```ts
export function validateRequiredWizardState({
  knowledgeBaseId,
  sourceType,
  feedName,
}: { /* ... */ }): ValidationIssue[] {
  const issues: ValidationIssue[] = []

  if (!knowledgeBaseId) {
    issues.push({ ...issue('missing-kb', 'Select a knowledge base before submitting.'), kind: 'prerequisite' })
  }
  if (!sourceType) {
    issues.push({ ...issue('missing-source', 'Choose Documents or Structured Records before submitting.'), kind: 'prerequisite' })
  }
  if (sourceType === 'records' && !feedName) {
    issues.push({ ...issue('missing-feed', 'Select a structured records feed before submitting.'), kind: 'prerequisite' })
  }

  return issues
}
```

Severity stays `'error'` so the existing submit guards (`issues.some(i => i.severity === 'error')`) continue to block submission unchanged.

All other validators (`validateDocumentFiles`, `validateRecordFile`, `validateRecordRows`) and backend-error constructors in `KnowledgeBaseManagerPage.tsx` leave `kind` absent, which consumers treat as `'content'`.

### 3. Stepper logic — `KnowledgeBaseManagerPage.tsx`

Replace the `completedStepIds` / `errorStepIds` computation:

```ts
const contentErrors = currentIssues.filter(
  (i) => (i.kind ?? 'content') === 'content' && i.severity === 'error',
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

Behavioural matrix:

| State | Validate step shows |
|---|---|
| Cold load (no KB, no source, no files) | Idle (gray Circle, no chip) |
| KB selected, source picked, nothing uploaded | Idle |
| Files uploaded, all pass validation | Complete (green CheckCircle2 + "Complete") |
| Files uploaded, some fail validation | Error (red CircleAlert + "Needs attention") |
| Backend rejects a submission | Error (red CircleAlert + "Needs attention") |

### 4. ValidationPanel rendering — `ValidationPanel.tsx`

Render prerequisites as a separate top section above the source-grouped sections, with `info`-toned styling rather than `danger`. The component partitions `issues` into `prerequisites` and `content` issues, then renders them in two distinct visual regions.

Sketch of the new layout when both prerequisites and content errors exist:

```
┌─────────────────────────────────────────────┐
│ Prerequisites                  [2 to do]    │  Chip tone="info", count uses "to do" wording
│  ● Select a knowledge base...               │
│  ● Choose Documents or Structured Records...│
├─────────────────────────────────────────────┤
│ Client check                   [1 issue]    │  Existing source-grouped section (only content)
│  ⚠ Row 14 field NPI must be 10 digits.     │
└─────────────────────────────────────────────┘
```

When no prerequisites and no content issues remain, the panel falls back to the existing "Ready for submission" empty state.

When ONLY prerequisites remain (the cold-load case), the panel renders the Prerequisites section alone and skips the empty state — the user still gets useful direction, just without red error styling.

The per-item severity label inside the prerequisite list is rendered with a softer "to do" tone (small dot or info icon instead of the `error` chip). Concretely: prerequisite list items omit the `ingestion-validation-panel__severity--error` modifier and use a new `ingestion-validation-panel__severity--prerequisite` modifier styled in `ingestion.css`.

### 5. Submit guards

Unchanged. `submitDocuments()` and `submitRecords()` continue to re-run `validateRequiredWizardState` and block submission on `severity === 'error'`. Because the severity of prerequisite issues stays `'error'`, the guards correctly prevent submission until prerequisites are satisfied.

### 6. Testing

- `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts`
  - Update existing assertions to verify each issue emitted by `validateRequiredWizardState` has `kind: 'prerequisite'`.
  - Verify other validators (`validateDocumentFiles`, `validateRecordRows`) do NOT set `kind`.

- `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx`
  - Cold load: assert the Validate stepper item has neither error nor complete state — no "Needs attention" chip, no green "Complete" chip.
  - After uploading a known-bad file (e.g. an empty file when `validateDocumentFiles` flags it): assert Validate shows "Needs attention".
  - After uploading a clean file with a selected KB + source: assert Validate shows "Complete".
  - Submit blocking remains intact: clicking Submit Documents with no KB still does not invoke `uploadMutation.mutate`.

- `chili_app/src/components/ingestion/__tests__/ValidationPanel.test.tsx` (create if absent)
  - Renders an empty-state "Ready for submission" when no issues.
  - Renders the Prerequisites section with `info`-toned chip when only prerequisites are present.
  - Renders both Prerequisites and Client check sections when both are present.
  - Renders only Client check when there are content issues but no prerequisites.

### 7. Files touched

| File | Change |
|------|--------|
| `chili_app/src/lib/ingestion/types.ts` | Add `ValidationKind` type and `kind?: ValidationKind` field on `ValidationIssue` |
| `chili_app/src/lib/ingestion/validateIngestion.ts` | Tag `validateRequiredWizardState` output with `kind: 'prerequisite'` |
| `chili_app/src/lib/ingestion/__tests__/validateIngestion.test.ts` | Assert new field on prerequisite issues |
| `chili_app/src/pages/KnowledgeBaseManagerPage.tsx` | Split `currentIssues` by kind; update `completedStepIds` / `errorStepIds` |
| `chili_app/src/pages/__tests__/KnowledgeBaseManagerPage.test.tsx` | Cover stepper states across cold load and progression |
| `chili_app/src/components/ingestion/ValidationPanel.tsx` | Render prerequisites as a separate info-toned section |
| `chili_app/src/components/ingestion/ingestion.css` | Add `.ingestion-validation-panel__severity--prerequisite` styling |
| `chili_app/src/components/ingestion/__tests__/ValidationPanel.test.tsx` | Cover the new prerequisites section |

## Success Criteria

- On cold load of `/knowledge-bases`, the IngestionStepper renders the Validate step as idle (gray Circle, no chip). The stepper as a whole does not contain any red "Needs attention" chip.
- The ValidationPanel renders a "Prerequisites" section with info-toned styling listing the two required-state items. No red error chips appear in the panel.
- After the user selects a KB and picks a source type, the Validate step remains idle (no content yet to validate).
- After the user drops a file that fails `validateDocumentFiles` (e.g. an empty file), the Validate step flips to "Needs attention".
- After the user drops a clean file, the Validate step flips to "Complete".
- Submit Documents and Submit Records continue to block submission while any prerequisite is unsatisfied (verified by an existing submit-attempt test that the `uploadMutation.mutate` is not called).
- Vitest, ESLint, `tsc -b` all green. No new Playwright e2e flow required for this fix (the cold-load behaviour is adequately covered at the unit-test level).
