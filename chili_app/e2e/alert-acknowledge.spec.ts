/**
 * Alert acknowledgement (full stack). Clicking Ack POSTs to the real API and
 * the projection status transitions to acknowledged.
 */
import { test, expect } from '@playwright/test'

test.describe('Alert acknowledgement', () => {
  test('acknowledging the seeded alert persists via the real API', async ({ page }) => {
    await page.goto('/alerts')
    await expect(page.getByText('Redwood DME Group').first()).toBeVisible()

    const ackButton = page.getByRole('button', { name: 'Acknowledge' }).first()
    await expect(ackButton).toBeVisible()
    await ackButton.click()

    // After the real acknowledge mutation + refetch, an acknowledged control appears.
    await expect(page.getByRole('button', { name: 'Acknowledged' }).first()).toBeVisible()
  })
})
