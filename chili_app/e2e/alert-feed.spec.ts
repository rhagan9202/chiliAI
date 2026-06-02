/**
 * Alert Feed (full stack). The seeded alert (POST /admin/dev-seed) is served by
 * the real alert projection and rendered on the feed.
 */
import { test, expect } from '@playwright/test'

test.describe('Alert Feed', () => {
  test('renders the seeded alert with severity and filter controls', async ({ page }) => {
    await page.goto('/alerts')
    await expect(page.getByRole('heading', { name: 'Alert Feed' })).toBeVisible()
    await expect(page.getByText('Redwood DME Group').first()).toBeVisible()
    await expect(page.getByText('Provider activity is materially above peers.').first()).toBeVisible()
    // Filter controls.
    await expect(page.getByRole('button', { name: 'Critical' })).toBeVisible()
  })
})
