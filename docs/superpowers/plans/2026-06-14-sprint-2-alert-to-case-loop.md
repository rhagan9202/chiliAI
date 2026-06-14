# Sprint 2 Alert To Case Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let analysts act on the exact alert they selected, promote that alert into a durable case, submit meaningful feedback, and refresh with case status and feedback still present.

**Architecture:** Move analyst feedback from `request.app.state.case_feedback` into the durable case repository. Resolve case-linked alerts in `CaseDetailResponse.alerts`. Add frontend row-level alert actions and selectable feedback controls backed by existing React Query case hooks.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, durable case repository adapters, Alembic/Postgres when enabled, React 19, Vite, TanStack Query, Vitest.

**Spec:** [docs/superpowers/specs/2026-06-14-demoable-workflow-increments-design.md](../specs/2026-06-14-demoable-workflow-increments-design.md)

---

## File Structure

- Modify: `backend/cases/models.py` — add `AnalystFeedback` and `Case.feedback_history`.
- Modify: `backend/cases/service.py` — add durable feedback append behavior.
- Modify: `backend/cases/adapters/postgres.py` — persist `feedback_history` JSONB.
- Review/modify: `backend/cases/adapters/in_memory.py` — verify model-copy behavior preserves feedback.
- Create: `backend/database/migrations/versions/0007_case_feedback.py` — add/drop `cases.feedback_history`.
- Modify: `backend/api/dependencies.py` — remove in-memory feedback store, map durable feedback, resolve linked alerts.
- Modify: `backend/cases/README.md` — document durable feedback.
- Modify: `backend/tests/cases/test_service.py`
- Modify: `backend/tests/api/test_phase5_stateful_routes.py`
- Modify: `backend/tests/api/test_read_model_routers.py`
- Modify: `chili_app/src/api/cases.ts` — add selected-alert promotion mutation.
- Modify: `chili_app/src/pages/AlertFeedPage.tsx` — add row actions.
- Modify: `chili_app/src/pages/CaseManagementPage.tsx` — promote clicked alert and collect selectable feedback.
- Modify: `chili_app/src/api/__tests__/cases.test.ts`
- Modify: `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx`
- Modify: `chili_app/src/pages/__tests__/CaseManagementPage.test.tsx`
- Regenerate if Pydantic contracts change: `chili_app/openapi.json`, `chili_app/src/lib/api/schema.ts`.

## Task 1: Persist Case Feedback In The Case Domain

**Files:**
- Modify: `backend/cases/models.py`
- Modify: `backend/cases/service.py`
- Modify: `backend/cases/adapters/postgres.py`
- Create: `backend/database/migrations/versions/0007_case_feedback.py`
- Modify: `backend/tests/cases/test_service.py`

- [ ] **Step 1: Add the failing service test**

```python
def test_add_feedback_persists_on_case() -> None:
    service = create_case_service(InMemoryCaseRepository())
    case = service.create(
        knowledge_base_id="kb-1",
        title="Escalation",
        priority="high",
        alert_ids=["alert-1"],
    )

    updated = service.add_feedback(
        knowledge_base_id="kb-1",
        case_id=case.id,
        label="insufficient_evidence",
        evidence_adequacy="medium",
        missing_evidence=["prior authorization records"],
        notes="Need prior authorization before closing.",
    )

    reloaded = service.get(knowledge_base_id="kb-1", case_id=case.id)
    assert reloaded is not None
    assert updated.feedback_history[-1].label == "insufficient_evidence"
    assert reloaded.feedback_history[-1].missing_evidence == ["prior authorization records"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
uv run --project backend pytest backend/tests/cases/test_service.py::test_add_feedback_persists_on_case -q
```

Expected: FAIL because `CaseService.add_feedback` does not exist.

- [ ] **Step 3: Add domain feedback types in `backend/cases/models.py`**

```python
FeedbackLabel = Literal["suspicious", "not_suspicious", "insufficient_evidence"]
EvidenceAdequacy = Literal["low", "medium", "high"]

class AnalystFeedback(BaseModel):
    case_id: str
    label: FeedbackLabel
    evidence_adequacy: EvidenceAdequacy
    missing_evidence: list[str] = Field(default_factory=lambda: cast(list[str], []))
    notes: str
    submitted_at: datetime = Field(default_factory=utc_now)
```

Add this field to `Case`:

```python
feedback_history: list[AnalystFeedback] = Field(default_factory=lambda: cast(list[AnalystFeedback], []))
```

- [ ] **Step 4: Implement `CaseService.add_feedback`**

```python
def add_feedback(
    self,
    *,
    knowledge_base_id: str,
    case_id: str,
    label: FeedbackLabel,
    evidence_adequacy: EvidenceAdequacy,
    missing_evidence: Sequence[str],
    notes: str,
) -> Case:
    case = self.get(knowledge_base_id=knowledge_base_id, case_id=case_id)
    if case is None:
        raise CaseNotFoundError(case_id)
    updated = case.model_copy(
        update={
            "feedback_history": [
                *case.feedback_history,
                AnalystFeedback(
                    case_id=case.id,
                    label=label,
                    evidence_adequacy=evidence_adequacy,
                    missing_evidence=list(missing_evidence),
                    notes=notes,
                ),
            ],
            "updated_at": utc_now(),
        },
        deep=True,
    )
    return self.repository.update(updated)
```

- [ ] **Step 5: Add the migration**

```python
"""Add durable case feedback history."""

from __future__ import annotations

from alembic import op

revision = "0007_case_feedback"
down_revision = "0006_entity_derived_signals"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute(
        "ALTER TABLE cases "
        "ADD COLUMN feedback_history jsonb NOT NULL DEFAULT '[]'::jsonb"
    )

def downgrade() -> None:
    op.execute("ALTER TABLE cases DROP COLUMN IF EXISTS feedback_history")
```

- [ ] **Step 6: Persist feedback in the Postgres adapter**

Include `feedback_history` in insert/update columns, serialize with `model_dump(mode="json")`, and decode each stored item with `AnalystFeedback.model_validate(item)`. Raise:

```python
CasePersistenceError("cases.feedback_history did not decode to a list.")
```

when malformed storage is encountered.

- [ ] **Step 7: Run backend checks**

Run:

```bash
uv run --project backend pytest backend/tests/cases/test_service.py -q
uv run --project backend pyright
```

Expected: service tests and typecheck pass.

## Task 2: Return Durable Feedback And Linked Alerts From Case Detail

**Files:**
- Modify: `backend/api/dependencies.py`
- Modify: `backend/tests/api/test_phase5_stateful_routes.py`
- Modify: `backend/tests/api/test_read_model_routers.py`
- Modify: `backend/cases/README.md`

- [ ] **Step 1: Add failing API assertions**

Extend case route tests to assert that after posting feedback, a fresh `GET /cases/{case_id}` contains the feedback history, and that promoted cases contain linked alert summaries.

```python
detail = client.get(f"/cases/{case_id}", params={"knowledge_base_id": "kb-1"})
payload = detail.json()
assert payload["feedback_history"][-1]["label"] == "insufficient_evidence"
assert payload["feedback_history"][-1]["missing_evidence"] == ["prior authorization records"]
assert payload["alerts"][0]["id"] == "alert-001"
assert payload["alerts"][0]["knowledge_base_id"] == "kb-1"
```

- [ ] **Step 2: Run the failing API tests**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_create_and_update_case_and_append_feedback backend/tests/api/test_phase5_stateful_routes.py::test_promote_alert_to_case_captures_origin_and_evidence backend/tests/api/test_read_model_routers.py::test_get_case_detail_returns_durable_case -q
```

Expected: feedback is still ephemeral and/or `alerts` is empty.

- [ ] **Step 3: Remove app-state feedback storage**

Delete `get_case_feedback_store()` from `backend/api/dependencies.py` and remove all `request.app.state.case_feedback` usage.

- [ ] **Step 4: Resolve case alerts in `_assemble_case_detail`**

Change `_assemble_case_detail` to accept an alert repository and return linked alerts for `case.alert_ids`, filtered to the same KB.

```python
alerts=[
    _alert_projection_to_response(record.alert)
    for alert_id in case.alert_ids
    if (record := alert_repository.get(alert_id)) is not None
    and record.knowledge_base_id == case.knowledge_base_id
]
```

- [ ] **Step 5: Map durable feedback into response DTOs**

```python
feedback_history=[
    AnalystFeedbackResponse(
        case_id=feedback.case_id,
        label=feedback.label,
        evidence_adequacy=feedback.evidence_adequacy,
        missing_evidence=list(feedback.missing_evidence),
        notes=feedback.notes,
        submitted_at=feedback.submitted_at,
    )
    for feedback in case.feedback_history
]
```

- [ ] **Step 6: Update feedback payload provider**

Call `service.add_feedback(...)` with `payload.label`, `payload.evidence_adequacy`, `payload.missing_evidence`, and `payload.notes`, then assemble detail from the returned case.

- [ ] **Step 7: Update documentation**

In `backend/cases/README.md`, replace any statement that analyst feedback is ephemeral with durable-on-case-record behavior.

- [ ] **Step 8: Run backend checks**

Run:

```bash
uv run --project backend pytest backend/tests/api/test_phase5_stateful_routes.py::test_create_and_update_case_and_append_feedback backend/tests/api/test_phase5_stateful_routes.py::test_promote_alert_to_case_captures_origin_and_evidence backend/tests/api/test_read_model_routers.py::test_get_case_detail_returns_durable_case -q
uv run --project backend pyright
```

Expected: focused API tests and typecheck pass.

- [ ] **Step 9: Regenerate contracts only if API contracts changed**

Run from repo root if Pydantic response/request models changed:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
```

Expected: generated OpenAPI/schema drift is intentional and checked in.

## Task 3: Promote The Exact Alert From Alert Feed

**Files:**
- Modify: `chili_app/src/api/cases.ts`
- Modify: `chili_app/src/pages/AlertFeedPage.tsx`
- Modify: `chili_app/src/api/__tests__/cases.test.ts`
- Modify: `chili_app/src/pages/__tests__/AlertFeedPage.test.tsx`

- [ ] **Step 1: Add failing API/client test for selected-alert promotion**

```ts
await promoteAlertToCase({ knowledgeBaseId: 'kb-1', alertId: 'alert-2' })

expect(fetchMock).toHaveBeenCalledWith(
  expect.stringContaining('/cases/promote?knowledge_base_id=kb-1'),
  expect.objectContaining({ body: JSON.stringify({ alert_id: 'alert-2' }) }),
)
```

- [ ] **Step 2: Add the client helper and hook**

```ts
export type PromoteAlertToCaseInput = {
  knowledgeBaseId: string
  alertId: string
  notes?: string
}

export function promoteAlertToCase({
  knowledgeBaseId,
  alertId,
  notes,
}: PromoteAlertToCaseInput): Promise<CaseDetailResponse> {
  return promoteCase(knowledgeBaseId, { alert_id: alertId, notes })
}

export function usePromoteAlertToCase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: promoteAlertToCase,
    onSuccess: (_detail, variables) => {
      void queryClient.invalidateQueries({ queryKey: casesQueryKey(variables.knowledgeBaseId) })
    },
  })
}
```

- [ ] **Step 3: Add row actions to `AlertFeedPage.tsx`**

For each alert row, keep existing `Ack` and `View evidence`; add:

```tsx
<Link
  className="page-button page-button--sm page-button--secondary"
  to={`/investigation/${encodeURIComponent(alert.entity_id)}?kb=${encodeURIComponent(alert.knowledge_base_id)}`}
>
  Investigate entity
</Link>
<button
  className="page-button page-button--sm"
  disabled={promoteMutation.isPending}
  onClick={() =>
    promoteMutation.mutate(
      { knowledgeBaseId: alert.knowledge_base_id, alertId: alert.id },
      { onSuccess: () => showToast('success', `Promoted ${alert.entity_label} to a case.`) },
    )
  }
  type="button"
>
  Promote to case
</button>
```

- [ ] **Step 4: Add page tests**

Assert clicking the second alert's promote button calls the mutation with `alert-2`, and that the investigate link includes the row entity and KB.

- [ ] **Step 5: Run frontend checks**

Run:

```bash
cd chili_app
npm run test:run -- src/api/__tests__/cases.test.ts src/pages/__tests__/AlertFeedPage.test.tsx
```

Expected: tests pass.

## Task 4: Capture Meaningful Case Feedback In The UI

**Files:**
- Modify: `chili_app/src/pages/CaseManagementPage.tsx`
- Modify: `chili_app/src/pages/__tests__/CaseManagementPage.test.tsx`
- Modify: `chili_app/src/pages/pages.css` only if spacing needs it.

- [ ] **Step 1: Add failing tests for clicked-alert promotion and selectable feedback**

Test that each unpromoted alert renders its own promote button, and that feedback submission sends exact selected label, adequacy, missing evidence, and notes.

```ts
expect(mocks.promote).toHaveBeenCalledWith(
  { alert_id: 'alert-3' },
  expect.anything(),
)

expect(mocks.addFeedback).toHaveBeenCalledWith(
  {
    label: 'insufficient_evidence',
    evidence_adequacy: 'medium',
    missing_evidence: ['claims history', 'prior auth'],
    notes: 'Need more records.',
  },
  expect.anything(),
)
```

- [ ] **Step 2: Replace single-alert promotion with per-alert actions**

Replace `unpromotedAlert` with:

```tsx
const unpromotedAlerts = alertsQuery.data.items.filter(
  (alert) => !casesQuery.data.items.some((existingCase) => existingCase.alert_ids.includes(alert.id)),
)
```

Render one `Promote {alert.entity_label} to case` button per alert.

- [ ] **Step 3: Add feedback form state**

```tsx
const [feedbackLabel, setFeedbackLabel] = useState<CaseFeedbackCreateRequest['label']>('suspicious')
const [evidenceAdequacy, setEvidenceAdequacy] = useState<CaseFeedbackCreateRequest['evidence_adequacy']>('high')
const [missingEvidence, setMissingEvidence] = useState('')
const [feedbackNotes, setFeedbackNotes] = useState('')
```

- [ ] **Step 4: Render label and adequacy controls**

Use selects or segmented controls with these exact values:

- Label: `suspicious`, `not_suspicious`, `insufficient_evidence`
- Evidence adequacy: `high`, `medium`, `low`

- [ ] **Step 5: Submit parsed feedback**

```tsx
feedbackMutation.mutate(
  {
    label: feedbackLabel,
    evidence_adequacy: evidenceAdequacy,
    missing_evidence: missingEvidence
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    notes: feedbackNotes,
  },
  {
    onSuccess: () => showToast('success', 'Feedback saved.'),
    onError: () => showToast('error', 'Could not save feedback.'),
  },
)
```

- [ ] **Step 6: Render feedback history with all fields**

Display label, evidence adequacy, notes, and missing evidence entries, not only label and notes.

- [ ] **Step 7: Run frontend checks**

Run:

```bash
cd chili_app
npm run test:run -- src/pages/__tests__/CaseManagementPage.test.tsx
npm run build
```

Expected: page tests and build pass.

## Task 5: Final Verification

**Files:**
- All touched backend/frontend files.

- [ ] **Step 1: Run focused backend suite**

Run:

```bash
uv run --project backend pytest backend/tests/cases/test_service.py backend/tests/api/test_phase5_stateful_routes.py backend/tests/api/test_read_model_routers.py -q
uv run --project backend pyright
```

Expected: backend tests and typecheck pass.

- [ ] **Step 2: Run focused frontend suite and build**

Run:

```bash
cd chili_app
npm run test:run -- src/api/__tests__/cases.test.ts src/pages/__tests__/AlertFeedPage.test.tsx src/pages/__tests__/CaseManagementPage.test.tsx
npm run build
```

Expected: frontend tests and build pass.

- [ ] **Step 3: Verify generated contract drift if Pydantic changed**

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m tools.export_openapi --output chili_app/openapi.json
cd chili_app
npm run codegen:api
npm run build
```

Expected: regenerated files are either unchanged or intentionally included.

## Acceptance Checks

- [ ] Alert feed shows row actions: `Ack`, `View evidence` when available, `Investigate entity`, and `Promote to case`.
- [ ] Clicking `Investigate entity` navigates to `/investigation/<entity_id>?kb=<knowledge_base_id>`.
- [ ] Clicking `Promote to case` on the second visible alert creates a case whose `originating_alert_id` and `alert_ids` match that second alert.
- [ ] Case Management no longer promotes only the first unpromoted alert.
- [ ] Case detail includes linked alert summaries in `alerts`, evidence pack when present, timeline, and feedback history.
- [ ] Analyst feedback supports `suspicious`, `not_suspicious`, and `insufficient_evidence`.
- [ ] Analyst feedback supports `low`, `medium`, and `high` evidence adequacy plus explicit missing evidence.
- [ ] After refresh, the same case status and feedback history render from the backend.

## Demo Script

1. Open `/alerts`.
2. Select a high-risk alert and click `View evidence`.
3. Click `Investigate entity`, then return to the alert feed.
4. Click `Promote to case` on that same alert.
5. Open `/cases?kb=<alert-kb>`.
6. Confirm the promoted case is selected or visible.
7. Mark it `In review`.
8. Save feedback with `insufficient_evidence`, `medium`, missing evidence, and notes.
9. Refresh and confirm status plus feedback history remain visible.
