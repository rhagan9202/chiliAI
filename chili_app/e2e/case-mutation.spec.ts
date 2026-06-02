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

    const detailPanel = page.locator('.case-layout')
    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'open' })).toBeVisible()

    await page.getByRole('button', { name: 'Mark in review' }).click()

    await expect(detailPanel.locator('.ui-chip').filter({ hasText: 'in_review' })).toBeVisible()
  })
})
