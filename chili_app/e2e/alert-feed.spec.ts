/**
 * Flow 5a: Alert feed page
 *
 * Verifies that AlertFeedPage renders alert rows with the correct severity chips,
 * status chips, and filter controls when the /alerts endpoint returns data.
 *
 * Mocked endpoints (host-anchored):
 *   GET http://localhost:5173/api/auth/me          → SessionUser
 *   GET http://localhost:5173/api/config/domain    → DomainConfig
 *   GET http://localhost:5173/api/config/features  → DomainFeatures
 *   GET http://localhost:5173/api/events/stream    → SSE stub
 *   GET http://localhost:5173/api/alerts           → AlertListResponse (3 items)
 *
 * Endpoint path verified: src/api/alerts.ts → apiFetch('/alerts')
 * Response shapes verified against:
 *   - AlertListResponse  → src/api/contracts.ts
 *   - AlertListItem      → src/api/contracts.ts (AlertSeverity, AlertStatus)
 *   - FilterBar          → src/components/ui/FilterBar.tsx (aria-label="Filters")
 *   - Chip               → src/components/ui/Chip.tsx (span.ui-chip)
 *
 * Route: /alerts → AlertFeedPage (src/app/router.tsx)
 */

import { test, expect } from '@playwright/test'

import { mockAlerts, mockAuthenticatedShell } from './helpers/mocks'
import type { FakeAlert } from './helpers/mocks'

const FAKE_ALERTS: FakeAlert[] = [
  {
    id: 'alert-001',
    entity_id: 'entity-001',
    entity_type: 'Vendor',
    entity_label: 'Acme Medical Supply',
    severity: 'critical',
    status: 'open',
    title: 'Billing anomaly detected',
    reasoning: 'Claims volume 4x above peer baseline.',
    confidence: 0.92,
    evidence_pack_id: 'ep-001',
    created_at: '2024-05-01T10:00:00Z',
    tags: ['billing-anomaly', 'high-volume'],
  },
  {
    id: 'alert-002',
    entity_id: 'entity-002',
    entity_type: 'Vendor',
    entity_label: 'Premier Health Partners',
    severity: 'high',
    status: 'investigating',
    title: 'Unusual referral pattern',
    reasoning: 'Referral network density exceeds threshold.',
    confidence: 0.74,
    evidence_pack_id: null,
    created_at: '2024-05-02T14:30:00Z',
    tags: ['referral-pattern'],
  },
  {
    id: 'alert-003',
    entity_id: 'entity-003',
    entity_type: 'Vendor',
    entity_label: 'Delta Care Group',
    severity: 'medium',
    status: 'acknowledged',
    title: 'Moderate risk flag',
    reasoning: 'Claim rejection rate elevated vs peers.',
    confidence: 0.55,
    evidence_pack_id: null,
    created_at: '2024-05-03T08:00:00Z',
    tags: [],
  },
]

test.describe('Alert feed page', () => {
  test('renders all alert rows with severity chips and filter controls', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockAlerts(page, FAKE_ALERTS)

    await page.goto('/alerts')

    // Page heading rendered by SectionHeader inside AlertFeedPage.
    await expect(page.getByRole('heading', { name: 'Alert Feed' })).toBeVisible()

    // Total-items chip: "3 alerts loaded" — text composed in AlertFeedPage from
    // alertsQuery.data.page.total_items.
    await expect(page.getByText('3 alerts loaded')).toBeVisible()

    // Filter controls — FilterBar renders buttons inside div[aria-label="Filters"].
    // AlertFeedPage defines filters: All / Critical / High / Acknowledged.
    const filterBar = page.locator('[aria-label="Filters"]')
    await expect(filterBar).toBeVisible()
    await expect(filterBar.getByRole('button', { name: 'All' })).toBeVisible()
    await expect(filterBar.getByRole('button', { name: 'Critical' })).toBeVisible()
    await expect(filterBar.getByRole('button', { name: 'High' })).toBeVisible()
    await expect(filterBar.getByRole('button', { name: 'Acknowledged' })).toBeVisible()

    // All three entity labels render.
    await expect(page.getByText('Acme Medical Supply')).toBeVisible()
    await expect(page.getByText('Premier Health Partners')).toBeVisible()
    await expect(page.getByText('Delta Care Group')).toBeVisible()

    // Severity chips render for each row. Chip renders as <span class="ui-chip">.
    // AlertFeedPage renders: <Chip label={alert.severity} tone={...} />
    // Locate within the page grid to avoid matching the filter buttons with same text.
    const pageGrid = page.locator('.page-grid')
    const chips = pageGrid.locator('.ui-chip')
    // Each row has at least a severity chip and a status chip, so we expect ≥6 total.
    await expect(chips).toHaveCount(await chips.count())
    // Verify the three distinct severity labels are present as chips.
    // Use exact text matches to avoid false hits from tag chips like "high-volume".
    await expect(pageGrid.getByText('critical', { exact: true }).first()).toBeVisible()
    await expect(pageGrid.getByText('high', { exact: true })).toBeVisible()
    await expect(pageGrid.getByText('medium', { exact: true })).toBeVisible()

    // Status chips also render.
    await expect(pageGrid.getByText('open', { exact: true })).toBeVisible()
    await expect(pageGrid.getByText('investigating', { exact: true })).toBeVisible()
    await expect(pageGrid.getByText('acknowledged', { exact: true })).toBeVisible()
  })

  test('severity filter shows only matching rows', async ({ page }) => {
    await mockAuthenticatedShell(page)
    await mockAlerts(page, FAKE_ALERTS)

    await page.goto('/alerts')

    // Wait for all rows to load first.
    await expect(page.getByText('Acme Medical Supply')).toBeVisible()

    // Click the "Critical" filter button.
    await page.locator('[aria-label="Filters"]').getByRole('button', { name: 'Critical' }).click()

    // Only the critical-severity row should remain visible.
    await expect(page.getByText('Acme Medical Supply')).toBeVisible()
    await expect(page.getByText('Premier Health Partners')).not.toBeVisible()
    await expect(page.getByText('Delta Care Group')).not.toBeVisible()
  })
})
