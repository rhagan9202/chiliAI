/**
 * Flow 7b: Case feedback submission (KB-scoped, BL-010)
 *
 * Filling the analyst feedback textarea and clicking "Save suspicious finding":
 *   1. Fires POST /api/cases/:id/feedback?knowledge_base_id= with the correct body.
 *   2. After mutation success the feedback history shows the submitted note
 *      (cache invalidation → detail refetch).
 *
 * Cases are KB-scoped; route patterns and request predicates are query-tolerant.
 *
 * Route: /cases → CaseManagementPage (src/app/router.tsx)
 */

import { expect, test } from '@playwright/test'

import { mockAlerts, mockAuthenticatedShell, mockCases, mockKnowledgeBases } from './helpers/mocks'
import type { FakeAlert, FakeCase, FakeKnowledgeBase } from './helpers/mocks'

const FAKE_KBS: FakeKnowledgeBase[] = [
  {
    id: 'kb-1',
    name: 'Medicare Fraud',
    description: 'Primary exemplar',
    status: 'ready',
    document_count: 3,
    entity_count: 12,
    relationship_count: 8,
    created_at: '2024-06-01T00:00:00Z',
  },
]

const OPEN_CASE: FakeCase = {
  id: 'case-fb-1',
  knowledge_base_id: 'kb-1',
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
  evidence_pack: null,
  entity_timeline: [],
  feedback_history: [],
}

const NOTES_TEXT = 'Unusual billing pattern consistent with upcoding scheme.'

const DETAIL_WITH_FEEDBACK = {
  case: OPEN_CASE,
  alerts: [],
  evidence_pack: null,
  entity_timeline: [],
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
    await mockKnowledgeBases(page, FAKE_KBS)
    await mockAlerts(page, NO_ALERTS)
    await mockCases(page, [OPEN_CASE])

    // POST feedback route (registered before the detail route so it matches first).
    await page.route(/\/api\/cases\/case-fb-1\/feedback(?:\?.*)?$/, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DETAIL_WITH_FEEDBACK),
      })
    })

    // GET detail returns initial, then the version with feedback after mutation.
    let caseGetCount = 0
    await page.route(/\/api\/cases\/case-fb-1(?:\?.*)?$/, (route) => {
      if (route.request().method() === 'GET') {
        caseGetCount++
        const payload = caseGetCount === 1 ? INITIAL_DETAIL : DETAIL_WITH_FEEDBACK
        void route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(payload),
        })
      } else {
        void route.continue()
      }
    })

    await page.goto('/cases?kb=kb-1')

    await expect(page.getByText('Delta Pharma review').first()).toBeVisible()

    await expect(page.getByRole('button', { name: 'Save suspicious finding' })).toBeDisabled()

    await page.getByPlaceholder('Document the current evidence assessment').fill(NOTES_TEXT)

    await expect(page.getByRole('button', { name: 'Save suspicious finding' })).toBeEnabled()

    const postRequest = page.waitForRequest(
      (req) =>
        req.url().split('?')[0].endsWith('/cases/case-fb-1/feedback') &&
        req.method() === 'POST',
    )

    await page.getByRole('button', { name: 'Save suspicious finding' }).click()

    const req = await postRequest
    const body: unknown = req.postDataJSON()
    expect(body).toStrictEqual({
      label: 'suspicious',
      evidence_adequacy: 'high',
      missing_evidence: [],
      notes: NOTES_TEXT,
    })

    await expect(page.getByText('suspicious')).toBeVisible()
    await expect(page.getByText(NOTES_TEXT)).toBeVisible()
  })
})
