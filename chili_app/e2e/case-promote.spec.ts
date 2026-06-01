/**
 * Flow 7c: Promote an alert into a case (KB-scoped, BL-010)
 *
 * On the Cases page, an unpromoted alert renders a "Promote … to case" button.
 * Clicking it:
 *   1. Fires POST /api/cases/promote?knowledge_base_id= with body { alert_id }.
 *   2. On success the promoted case is auto-selected and its detail panel renders.
 *
 * Route: /cases → CaseManagementPage (src/app/router.tsx)
 */

import { expect, test } from '@playwright/test'

import {
  mockAlerts,
  mockAuthenticatedShell,
  mockCaseDetail,
  mockCases,
  mockKnowledgeBases,
  mockPromoteCase,
} from './helpers/mocks'
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

const UNPROMOTED_ALERT: FakeAlert = {
  id: 'alert-np-1',
  knowledge_base_id: 'kb-1',
  entity_id: 'provider-118',
  entity_type: 'provider',
  entity_label: 'North Harbor Imaging',
  severity: 'high',
  status: 'open',
  title: 'Referral concentration anomaly',
  reasoning: 'Referral traffic is concentrated outside norms.',
  confidence: 0.84,
  evidence_pack_id: 'ev-1',
  created_at: '2024-06-12T09:00:00Z',
  tags: ['network'],
}

const PROMOTED_CASE: FakeCase = {
  id: 'case-promoted-1',
  knowledge_base_id: 'kb-1',
  title: 'Investigation: Referral concentration anomaly',
  status: 'open',
  priority: 'high',
  assignee: null,
  alert_ids: ['alert-np-1'],
  updated_at: '2024-06-12T10:00:00Z',
}

test.describe('Promote alert to case', () => {
  test('POST /cases/promote fires with alert_id and the case detail renders', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, FAKE_KBS)
    await mockAlerts(page, [UNPROMOTED_ALERT])
    // Empty queue → the alert is unpromoted → promote button shows.
    await mockCases(page, [])
    await mockPromoteCase(page, { case: PROMOTED_CASE })
    await mockCaseDetail(page, 'case-promoted-1', { case: PROMOTED_CASE })

    await page.goto('/cases?kb=kb-1')

    const promoteButton = page.getByRole('button', { name: 'Promote North Harbor Imaging to case' })
    await expect(promoteButton).toBeVisible()

    const promoteRequest = page.waitForRequest(
      (req) => req.url().split('?')[0].endsWith('/cases/promote') && req.method() === 'POST',
    )

    await promoteButton.click()

    const req = await promoteRequest
    const body: unknown = req.postDataJSON()
    expect(body).toStrictEqual({ alert_id: 'alert-np-1' })

    // The promoted case is auto-selected; its detail panel renders.
    const detailPanel = page.locator('.case-layout')
    await expect(
      detailPanel.getByText('Investigation: Referral concentration anomaly'),
    ).toBeVisible()
  })
})
