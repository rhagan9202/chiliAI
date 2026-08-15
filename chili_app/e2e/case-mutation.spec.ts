/**
 * Case status mutation (full stack). "Mark in review" PATCHes the real API and
 * the detail status chip updates after refetch.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Case status mutation', () => {
  test('marking the seeded case in review persists via the real API', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/cases?kb=${kb}`)

    // The queue rows carry compact pills for the same case; the detail card's
    // are full size, so the detail assertion scopes to those.
    const detailPanel = page.locator('.case-layout .status-pill:not(.status-pill--compact)')
    await expect(detailPanel.and(page.getByLabel('Case status: open'))).toBeVisible()

    await page.getByRole('button', { name: 'Mark in review' }).click()

    await expect(detailPanel.and(page.getByLabel('Case status: in_review'))).toBeVisible()
  })
})
