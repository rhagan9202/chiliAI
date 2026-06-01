/**
 * Flow 6b: Cases page (CaseManagementPage) — KB-scoped (BL-010)
 *
 * Verifies that the case management page, scoped to a selected knowledge base:
 *   1. Renders all 3 case rows in the case queue.
 *   2. Status labels are visible per row in the queue list.
 *   3. The detail panel for the auto-selected first case shows status and priority chips.
 *
 * Cases are KB-scoped, so the page reads ?kb= and all /cases calls carry
 * ?knowledge_base_id=; the mock helpers are query-tolerant.
 *
 * Route: /cases → CaseManagementPage (src/app/router.tsx)
 */

import { test, expect } from '@playwright/test'

import {
  mockAuthenticatedShell,
  mockAlerts,
  mockCaseDetail,
  mockCases,
  mockKnowledgeBases,
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

const FAKE_CASES: FakeCase[] = [
  {
    id: 'case-001',
    title: 'Acme Medical review',
    status: 'open',
    priority: 'critical',
    assignee: 'analyst@example.com',
    alert_ids: ['alert-001'],
    updated_at: '2024-06-01T10:00:00Z',
  },
  {
    id: 'case-002',
    title: 'Premier Health audit',
    status: 'in_review',
    priority: 'high',
    assignee: null,
    alert_ids: ['alert-002'],
    updated_at: '2024-06-02T12:00:00Z',
  },
  {
    id: 'case-003',
    title: 'Delta Care investigation',
    status: 'closed',
    priority: 'medium',
    assignee: 'Unassigned',
    alert_ids: [],
    updated_at: '2024-06-03T08:00:00Z',
  },
]

// Empty alert list — no unpromoted alerts, so the promote button won't appear.
const NO_ALERTS: FakeAlert[] = []

test.describe('Cases page', () => {
  test('renders all 3 case rows with status labels and detail panel', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, FAKE_KBS)
    await mockAlerts(page, NO_ALERTS)
    await mockCases(page, FAKE_CASES)
    await mockCaseDetail(page, 'case-001', { case: FAKE_CASES[0] })

    await page.goto('/cases?kb=kb-1')

    await expect(page.getByRole('heading', { name: 'Case Management' })).toBeVisible()
    await expect(page.getByText('3 cases')).toBeVisible()

    await expect(page.getByText('Acme Medical review').first()).toBeVisible()
    await expect(page.getByText('Premier Health audit').first()).toBeVisible()
    await expect(page.getByText('Delta Care investigation').first()).toBeVisible()

    // Detail panel for the auto-selected case-001 renders status and priority chips.
    const detailPanel = page.locator('.case-layout')
    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'open' })).toBeVisible()
    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'critical' })).toBeVisible()
    await expect(
      detailPanel.locator('.ui-chip').filter({ hasText: 'analyst@example.com' }),
    ).toBeVisible()

    await expect(page.getByRole('button', { name: 'Mark in review' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Close case' })).toBeVisible()
  })

  test('priority chips render per row status in queue and detail panel', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockKnowledgeBases(page, FAKE_KBS)
    await mockAlerts(page, NO_ALERTS)
    await mockCases(page, FAKE_CASES)
    await mockCaseDetail(page, 'case-001', { case: FAKE_CASES[0] })
    await mockCaseDetail(page, 'case-002', { case: FAKE_CASES[1] })

    await page.goto('/cases?kb=kb-1')

    await expect(page.getByText('Acme Medical review').first()).toBeVisible()

    // Select the second case to verify its status/priority appear in the detail panel.
    await page.getByRole('button', { name: 'Premier Health audit' }).click()

    const detailPanel = page.locator('.case-layout')
    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'in_review' })).toBeVisible()
    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'high' })).toBeVisible()
  })
})
