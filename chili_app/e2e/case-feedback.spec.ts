/**
 * Flow 7b: Case feedback submission
 *
 * Verifies that filling the analyst feedback textarea and clicking
 * "Save suspicious finding" on the case detail panel:
 *   1. Fires POST /api/cases/:id/feedback with the correct body shape.
 *   2. After mutation success the feedback history section shows the submitted note
 *      (via cache invalidation → GET /api/cases/:id refetch returning the new entry).
 *
 * The feedback form is always visible in the detail panel (no separate trigger button).
 * CaseManagementPage:
 *   - textarea placeholder: "Document the current evidence assessment"
 *   - button:               "Save suspicious finding" (disabled when notes is empty)
 *   - hardcoded payload:    { label: 'suspicious', evidence_adequacy: 'high',
 *                             missing_evidence: [], notes: <textarea value> }
 *
 * Mocked endpoints (host-anchored):
 *   GET  http://localhost:5173/api/auth/me          → SessionUser
 *   GET  http://localhost:5173/api/config/domain    → DomainConfig
 *   GET  http://localhost:5173/api/config/features  → DomainFeatures
 *   GET  http://localhost:5173/api/events/stream    → SSE stub
 *   GET  http://localhost:5173/api/cases            → CaseListResponse (1 open case)
 *   GET  http://localhost:5173/api/alerts           → AlertListResponse (empty)
 *   GET  http://localhost:5173/api/cases/case-fb-1  → CaseDetailResponse (no history,
 *                                                      then with 1 entry after refetch)
 *   POST http://localhost:5173/api/cases/case-fb-1/feedback → CaseDetailResponse
 *
 * Endpoint shapes verified against:
 *   - CaseFeedbackCreateRequest → src/api/contracts.ts:
 *       { label: FeedbackLabel; evidence_adequacy: EvidenceAdequacy;
 *         missing_evidence: string[]; notes: string }
 *   - addCaseFeedback           → src/api/cases.ts: apiPost('/cases/:id/feedback', payload)
 *   - useAddCaseFeedback        → src/api/cases.ts: invalidates casesQueryKey + caseDetailQueryKey
 *   - CaseManagementPage        → src/pages/CaseManagementPage.tsx
 *
 * Route: /cases → CaseManagementPage (src/app/router.tsx)
 */

import { expect, test } from '@playwright/test'

import { mockAlerts, mockAuthenticatedShell, mockCases } from './helpers/mocks'
import type { FakeAlert, FakeCase } from './helpers/mocks'

const OPEN_CASE: FakeCase = {
  id: 'case-fb-1',
  title: 'Delta Pharma review',
  status: 'open',
  priority: 'high',
  assignee: null,
  alert_ids: [],
  updated_at: '2024-06-11T09:00:00Z',
}

const NO_ALERTS: FakeAlert[] = []

const INITIAL_DETAIL = {
  case: OPEN_CASE,
  alerts: [],
  feedback_history: [],
}

const NOTES_TEXT = 'Unusual billing pattern consistent with upcoding scheme.'

const DETAIL_WITH_FEEDBACK = {
  case: OPEN_CASE,
  alerts: [],
  feedback_history: [
    {
      case_id: 'case-fb-1',
      label: 'suspicious',
      evidence_adequacy: 'high',
      missing_evidence: [],
      notes: NOTES_TEXT,
      submitted_at: '2024-06-11T10:00:00Z',
    },
  ],
}

test.describe('Case feedback submission', () => {
  test('POST fires with correct body and feedback history updates after refetch', async ({
    page,
  }) => {
    await mockAuthenticatedShell(page)
    await mockAlerts(page, NO_ALERTS)
    await mockCases(page, [OPEN_CASE])

    // GET requests return initial detail first, then the version with feedback after mutation.
    let caseGetCount = 0
    await page.route('http://localhost:5173/api/cases/case-fb-1', (route) => {
      if (route.request().method() === 'GET') {
        caseGetCount++
        const payload = caseGetCount === 1 ? INITIAL_DETAIL : DETAIL_WITH_FEEDBACK
        void route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(payload),
        })
      } else {
        // Should not be reached in this test — no PATCH expected.
        void route.continue()
      }
    })

    // POST /api/cases/case-fb-1/feedback → CaseDetailResponse.
    // addCaseFeedback → src/api/cases.ts: apiPost('/cases/:id/feedback', payload)
    await page.route('http://localhost:5173/api/cases/case-fb-1/feedback', (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DETAIL_WITH_FEEDBACK),
      })
    })

    await page.goto('/cases')

    // Wait for the detail panel to render the case title.
    await expect(page.getByText('Delta Pharma review').first()).toBeVisible()

    // The submit button starts disabled because the textarea is empty.
    // CaseManagementPage: disabled={feedbackNotes.trim().length === 0}
    await expect(page.getByRole('button', { name: 'Save suspicious finding' })).toBeDisabled()

    // Fill the feedback textarea.
    await page
      .getByPlaceholder('Document the current evidence assessment')
      .fill(NOTES_TEXT)

    // Button should now be enabled.
    await expect(page.getByRole('button', { name: 'Save suspicious finding' })).toBeEnabled()

    // Capture the outgoing POST before clicking.
    const postRequest = page.waitForRequest(
      (req) =>
        req.url() === 'http://localhost:5173/api/cases/case-fb-1/feedback' &&
        req.method() === 'POST',
    )

    await page.getByRole('button', { name: 'Save suspicious finding' }).click()

    // Assert the POST body matches CaseFeedbackCreateRequest exactly.
    // CaseManagementPage hardcodes label='suspicious', evidence_adequacy='high',
    // missing_evidence=[] and uses the textarea value as notes.
    const req = await postRequest
    const body: unknown = req.postDataJSON()
    expect(body).toStrictEqual({
      label: 'suspicious',
      evidence_adequacy: 'high',
      missing_evidence: [],
      notes: NOTES_TEXT,
    })

    // After mutation onSuccess, useAddCaseFeedback invalidates caseDetailQueryKey and
    // the detail panel refetches.  The second mock response returns the feedback entry.
    // CaseManagementPage renders feedback as: <strong>{feedback.label.replace(/_/g, ' ')}</strong>
    await expect(page.getByText('suspicious')).toBeVisible()
    await expect(page.getByText(NOTES_TEXT)).toBeVisible()
  })
})
