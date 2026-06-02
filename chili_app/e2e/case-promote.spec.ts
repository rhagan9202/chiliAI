/**
 * Promote alert to case (full stack, BL-010). The seeded alert is unpromoted;
 * promoting it POSTs /cases/promote and the promoted case is auto-selected, so
 * the detail panel (scoped via its status/priority chip row) shows the new
 * case whose title is derived from the originating alert.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Promote alert to case', () => {
  test('promoting the seeded alert creates a case via the real API', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/cases?kb=${kb}`)

    const promote = page.getByRole('button', { name: 'Promote Redwood DME Group to case' }).first()
    await expect(promote).toBeVisible()
    await promote.click()

    // The detail panel (the metric-stack carrying the chip row) shows the
    // auto-selected promoted case, whose title is derived from the alert.
    const detail = page
      .locator('.case-layout .metric-stack')
      .filter({ has: page.locator('.alert-row-card__meta') })
    await expect(detail.getByText('Investigation: Outlier billing concentration')).toBeVisible()
  })
})
