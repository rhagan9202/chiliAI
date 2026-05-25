/**
 * Flow 1: Authenticated shell
 *
 * Verifies that a mocked authenticated session causes the AppShell to render
 * with the sidebar nav, topbar, and no error boundary triggered.
 *
 * Mocked endpoints (all host-anchored to prevent matching Vite source URLs):
 *   GET http://localhost:5173/api/auth/me          → SessionUser
 *   GET http://localhost:5173/api/config/domain    → DomainConfig
 *   GET http://localhost:5173/api/config/features  → DomainFeatures
 *   GET http://localhost:5173/api/events/stream    → SSE stub
 *   GET http://localhost:5173/api/alerts           → AlertListResponse
 *   GET http://localhost:5173/api/analytics/overview → AnalyticsOverviewResponse
 *   GET http://localhost:5173/api/workflows        → WorkflowRunListResponse
 *
 * Sources verified against:
 *   SessionUser          → src/contexts/sessionContextValue.ts
 *   DomainConfig         → src/api/contracts.ts
 *   DomainFeatures       → src/api/contracts.ts
 *   AlertListResponse    → src/api/contracts.ts
 *   AnalyticsOverviewResponse → src/api/contracts.ts
 *   WorkflowRunListResponse → src/api/contracts.ts
 *
 * DashboardPage is the post-auth landing route (router.tsx: index → /dashboard).
 * It loads alerts, analytics overview, and workflows — all mocked here so the
 * page renders past its loading guard to the data-ready state.
 */

import { test, expect } from '@playwright/test'

import { mockAuthenticatedShell } from './helpers/mocks'

const API = 'http://localhost:5173/api'

test.describe('Authenticated shell', () => {
  test('sidebar nav and topbar render after auth + domain config load', async ({ page }) => {
    await mockAuthenticatedShell(page)

    // DashboardPage fetches /alerts, /analytics/overview, and /workflows.
    // Mock them so the page renders past the loading guard.
    await page.route(`${API}/alerts`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], page: { page: 1, page_size: 25, total_items: 0 } }),
      })
    })

    await page.route(`${API}/analytics/overview`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          active_alerts: 0,
          open_cases: 0,
          entities_monitored: 0,
          high_risk_entities: 0,
        }),
      })
    })

    await page.route(`${API}/workflows`, (route) => {
      void route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [] }),
      })
    })

    await page.goto('/dashboard')

    // The sidebar renders inside <aside aria-label="Primary navigation">.
    // Using CSS class locator as Playwright's ARIA complementary role with
    // name lookup is equivalent but .app-sidebar class is stable.
    const sidebar = page.locator('.app-sidebar')
    await expect(sidebar).toBeVisible()

    // Sidebar brand text is rendered unconditionally (AppShell always shows it).
    await expect(sidebar.getByText('chiliAI')).toBeVisible()

    // Nav links are derived from FAKE_DOMAIN_CONFIG.ui.navigation.pages.
    await expect(sidebar.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    await expect(sidebar.getByRole('link', { name: 'Alert Feed' })).toBeVisible()
    await expect(sidebar.getByRole('link', { name: 'Knowledge Bases' })).toBeVisible()

    // Topbar is a <header class="app-topbar"> rendered by TopBar component.
    // domain.display_name from FAKE_DOMAIN_CONFIG = "Test Domain".
    const topbar = page.locator('.app-topbar')
    await expect(topbar).toBeVisible()
    await expect(topbar.getByText('Test Domain')).toBeVisible()

    // No error boundary should have triggered.
    await expect(page.getByText('Something went wrong')).not.toBeVisible()
    await expect(
      page.getByText('Dashboard metrics could not be loaded from the API.'),
    ).not.toBeVisible()

    // Dashboard page heading is rendered by SectionHeader inside DashboardPage.
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })
})
