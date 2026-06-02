/**
 * Policy Intelligence (full stack). The policy queue is served by the real API
 * (config-driven seed); the page renders policy gap items.
 */
import { test, expect } from '@playwright/test'

test.describe('Policy Intelligence', () => {
  test('renders the policy gap queue from the real API', async ({ page }) => {
    await page.goto('/policy')

    await expect(page.getByRole('heading', { name: 'Policy Intelligence' })).toBeVisible()
    await expect(
      page.getByText('Repeated injection exception language creates inconsistent triage evidence').first(),
    ).toBeVisible()
  })
})
