/**
 * Flow 5c: View an alert's evidence pack from the Alert Feed (BL-006)
 *
 * Each alert with an evidence pack renders a "View evidence" toggle. Clicking it
 * fetches the KB-scoped pack and renders the EvidencePackViewer (reasoning +
 * metric snapshot).
 *
 * Route: /alerts → AlertFeedPage (src/app/router.tsx)
 */

import { expect, test } from '@playwright/test'

import { mockAlerts, mockAuthenticatedShell, mockEvidencePack } from './helpers/mocks'
import type { FakeAlert } from './helpers/mocks'

const ALERT: FakeAlert = {
  id: 'alert-ev-1',
  knowledge_base_id: 'kb-1',
  entity_id: 'provider-204',
  entity_type: 'provider',
  entity_label: 'Redwood DME Group',
  severity: 'critical',
  status: 'open',
  title: 'Outlier billing concentration',
  reasoning: 'Provider activity is materially above peers.',
  confidence: 0.96,
  evidence_pack_id: 'ev-1',
  created_at: '2024-06-12T09:00:00Z',
  tags: ['billing'],
}

test.describe('Alert Feed evidence viewer', () => {
  test('clicking "View evidence" renders the evidence pack reasoning and metrics', async ({
    page,
  }) => {
    await mockAuthenticatedShell(page)
    await mockAlerts(page, [ALERT])
    await mockEvidencePack(page, {
      id: 'ev-1',
      alert_id: 'alert-ev-1',
      reasoning: 'Elevated peer deviation across cardiac billing.',
      confidence: 0.82,
      scores: { overall: 0.82, upcoding: 0.7 },
      subgraph_node_ids: ['provider-204'],
      subgraph_edge_ids: [],
    })

    await page.goto('/alerts')

    await expect(page.getByText('Redwood DME Group')).toBeVisible()

    await page.getByRole('button', { name: 'View evidence' }).click()

    // EvidencePackViewer renders the reasoning and a confidence metric chip.
    await expect(page.getByText('Elevated peer deviation across cardiac billing.')).toBeVisible()
    await expect(page.getByText('confidence 82%')).toBeVisible()

    // Toggling hides it again.
    await page.getByRole('button', { name: 'Hide evidence' }).click()
    await expect(
      page.getByText('Elevated peer deviation across cardiac billing.'),
    ).not.toBeVisible()
  })
})
