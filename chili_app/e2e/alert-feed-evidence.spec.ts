/**
 * Alert Feed evidence viewer (full stack, BL-006). "View evidence" fetches the
 * real evidence pack and renders the EvidencePackViewer.
 */
import { test, expect } from '@playwright/test'

test.describe('Alert Feed evidence viewer', () => {
  test('View evidence renders the real evidence pack reasoning and metrics', async ({ page }) => {
    await page.goto('/alerts')
    await expect(page.getByText('Redwood DME Group').first()).toBeVisible()

    await page.getByRole('button', { name: 'View evidence' }).first().click()

    await expect(
      page.getByText('Provider billing concentration and upcoding indicate elevated fraud risk.'),
    ).toBeVisible()
    await expect(page.getByText('confidence 82%')).toBeVisible()
  })
})
