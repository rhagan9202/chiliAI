/**
 * Flow 6a: Alert acknowledgement mutation
 *
 * Verifies that clicking the Acknowledge button on an open alert row:
 *   1. Fires POST /api/alerts/:id/acknowledge with an empty-object body.
 *   2. The status chip on the row transitions from "open" to "acknowledged"
 *      after the mutation resolves and the list refetch completes.
 *
 * Mocked endpoints (host-anchored):
 *   GET  http://localhost:5173/api/auth/me                  → SessionUser
 *   GET  http://localhost:5173/api/config/domain            → DomainConfig
 *   GET  http://localhost:5173/api/config/features          → DomainFeatures
 *   GET  http://localhost:5173/api/events/stream            → SSE stub
 *   GET  http://localhost:5173/api/alerts  (1st call)       → one open alert
 *   POST http://localhost:5173/api/alerts/alert-ack-1/acknowledge → ApiEnvelope
 *   GET  http://localhost:5173/api/alerts  (2nd call)       → same alert acknowledged
 *
 * Endpoint shapes verified against:
 *   - acknowledgeAlert  → src/api/alerts.ts: apiPost('/alerts/:id/acknowledge', {})
 *   - ApiEnvelope       → src/api/contracts.ts
 *   - AlertListResponse → src/api/contracts.ts
 *   - AlertFeedPage     → src/pages/AlertFeedPage.tsx (Acknowledge button, status Chip)
 */

import { test, expect } from '@playwright/test'

import { mockAuthenticatedShell } from './helpers/mocks'
import type { FakeAlert } from './helpers/mocks'

const OPEN_ALERT: FakeAlert = {
  id: 'alert-ack-1',
  entity_id: 'entity-ack-1',
  entity_type: 'Vendor',
  entity_label: 'Beta Diagnostics',
  severity: 'high',
  status: 'open',
  title: 'Outlier billing pattern',
  reasoning: 'Claim frequency 3x above peer baseline.',
  confidence: 0.81,
  evidence_pack_id: null,
  created_at: '2024-06-01T09:00:00Z',
  tags: ['billing-outlier'],
}

const ACKNOWLEDGED_ALERT: FakeAlert = { ...OPEN_ALERT, status: 'acknowledged' }

test.describe('Alert acknowledgement mutation', () => {
  test('POST is sent and status chip transitions to acknowledged', async ({ page }) => {
    await mockAuthenticatedShell(page)

    // Track how many times GET /api/alerts is called so we can serve different
    // responses before and after the mutation.
    let alertGetCount = 0

    await page.route('http://localhost:5173/api/alerts', (route) => {
      alertGetCount++
      const payload = alertGetCount === 1
        ? [OPEN_ALERT]      // first fetch: row is open
        : [ACKNOWLEDGED_ALERT] // post-mutation refetch: row is acknowledged
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: payload,
          page: { page: 1, page_size: 25, total_items: 1 },
        }),
      })
    })

    // Mock the acknowledge POST — returns ApiEnvelope (verified: src/api/contracts.ts)
    await page.route(
      'http://localhost:5173/api/alerts/alert-ack-1/acknowledge',
      (route) => {
        void route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'accepted', message: 'Alert acknowledged.' }),
        })
      },
    )

    await page.goto('/alerts')

    // Wait for the initial row to render before acting.
    await expect(page.getByText('Beta Diagnostics')).toBeVisible()

    // The status chip should start as "open".
    const pageGrid = page.locator('.page-grid')
    await expect(pageGrid.getByText('open', { exact: true })).toBeVisible()

    // Capture the outgoing POST to assert its body.
    const acknowledgeRequest = page.waitForRequest(
      (req) =>
        req.url() === 'http://localhost:5173/api/alerts/alert-ack-1/acknowledge' &&
        req.method() === 'POST',
    )

    // Click the Acknowledge button.  AlertFeedPage renders a single button per
    // row with text "Acknowledge" (when status !== 'acknowledged').
    // Use exact: true to distinguish from the filter button "Acknowledged".
    await pageGrid.getByRole('button', { name: 'Acknowledge', exact: true }).click()

    // Confirm the POST was sent and carries an empty-object body.
    // src/api/alerts.ts: apiPost('/alerts/:id/acknowledge', {})
    const req = await acknowledgeRequest
    const body: unknown = req.postDataJSON()
    expect(body).toStrictEqual({})

    // After mutation onSuccess the query is invalidated and GET /api/alerts is
    // refetched.  The second mock response returns the acknowledged alert.
    // The status chip should now read "acknowledged".
    await expect(pageGrid.getByText('acknowledged', { exact: true })).toBeVisible()

    // The row-level button should now be disabled and relabelled "Acknowledged".
    // AlertFeedPage renders "Acknowledged" (past tense) when status === 'acknowledged'.
    // The filter bar also contains an "Acknowledged" button, so scope to .page-button
    // class to target only the per-row action button.
    await expect(pageGrid.locator('button.page-button', { hasText: 'Acknowledged' })).toBeDisabled()
  })
})
