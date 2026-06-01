/**
 * Flow 7a: Case status transition mutation (KB-scoped, BL-010)
 *
 * Clicking "Mark in review" on the case detail panel:
 *   1. Fires PATCH /api/cases/:id?knowledge_base_id= with body { status: 'in_review' }.
 *   2. After the mutation resolves and the cache is invalidated, the detail panel
 *      refetches and the status chip reflects the new status.
 *
 * Cases are KB-scoped; all /cases calls carry ?knowledge_base_id=, so the route
 * patterns and request predicates are query-tolerant.
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
  id: 'case-mut-1',
  knowledge_base_id: 'kb-1',
  title: 'Gamma Labs review',
  status: 'open',
  priority: 'high',
  assignee: 'analyst@example.com',
  alert_ids: ['alert-mut-1'],
  updated_at: '2024-06-10T09:00:00Z',
}

const IN_REVIEW_CASE: FakeCase = { ...OPEN_CASE, status: 'in_review' }

const NO_ALERTS: FakeAlert[] = []

const OPEN_CASE_DETAIL = {
  case: OPEN_CASE,
  alerts: [],
  evidence_pack: null,
  entity_timeline: [],
  feedback_history: [],
}

const IN_REVIEW_CASE_DETAIL = {
  case: IN_REVIEW_CASE,
  alerts: [],
  evidence_pack: null,
  entity_timeline: [],
  feedback_history: [],
}

test.describe('Case status mutation', () => {
  test('PATCH fires with correct body and status chip updates to in_review', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, FAKE_KBS)
    await mockAlerts(page, NO_ALERTS)
    await mockCases(page, [OPEN_CASE])

    // GET serves open then in_review; PATCH returns the updated detail.
    let caseGetCount = 0
    await page.route(/\/api\/cases\/case-mut-1(?:\?.*)?$/, (route) => {
      if (route.request().method() === 'GET') {
        caseGetCount++
        const payload = caseGetCount === 1 ? OPEN_CASE_DETAIL : IN_REVIEW_CASE_DETAIL
        void route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(payload),
        })
      } else {
        void route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(IN_REVIEW_CASE_DETAIL),
        })
      }
    })

    await page.goto('/cases?kb=kb-1')

    const detailPanel = page.locator('.case-layout')
    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'open' })).toBeVisible()

    const patchRequest = page.waitForRequest(
      (req) =>
        req.url().split('?')[0].endsWith('/cases/case-mut-1') && req.method() === 'PATCH',
    )

    await page.getByRole('button', { name: 'Mark in review' }).click()

    const req = await patchRequest
    const body: unknown = req.postDataJSON()
    expect(body).toStrictEqual({ status: 'in_review' })

    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'in_review' })).toBeVisible()
  })
})
