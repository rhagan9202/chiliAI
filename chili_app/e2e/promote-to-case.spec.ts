/**
 * Promotion reaches what it created (UXA-405).
 *
 * Promoting an alert succeeded with a well-worded toast that carried no link,
 * so the case the analyst had just made was unreachable from the feed. The
 * alert also still read OPEN and its button looked clickable again.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Promote to case', () => {
  test('the toast opens the case it created, and the alert reflects it', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    const promote = page.getByRole('button', { name: /^Promote .+ to case$/ }).first()
    // A previous spec in the same serial run may already have promoted it.
    test.skip(!(await promote.isVisible()), 'seeded alert already promoted')
    await promote.click()

    const toast = page.getByRole('status').filter({ hasText: /Promoted .+ to a case/ })
    await expect(toast).toBeVisible()

    // The alert now says it is promoted and refuses a second one.
    await expect(page.getByRole('button', { name: /^Promoted .+ to case$/ })).toBeDisabled()

    await toast.getByRole('link', { name: 'Open case' }).click()
    await expect(page).toHaveURL(/\/cases\?/)
    await expect(page).toHaveURL(/case=/)
    await expect(page.getByRole('heading', { level: 1, name: 'Case Management' })).toBeVisible()
  })

  test('the evidence pack is dated and says what it drew on', async ({ page }) => {
    const { knowledge_base_id: kb, alert_id: alertId } = seeded()
    // `?alert=` opens the panel directly; the toggle then reads "Hide evidence".
    await page.goto(`/alerts?kb=${kb}&alert=${alertId}`)

    const pack = page.getByTestId('evidence-pack-viewer')
    await expect(pack).toBeVisible()
    await expect(pack.getByText(/^Generated /)).toBeVisible()
    await expect(pack.getByText(/Evidence confidence \d+%/)).toBeVisible()
  })
})
