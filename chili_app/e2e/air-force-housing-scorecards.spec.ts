/**
 * Air Force Housing Scorecards (full stack). The dashboard route renders the
 * map-led executive operating picture and scorecard action surface through the
 * real API, even when no housing rows have been ingested yet.
 */
import { expect, test } from '@playwright/test'

test.describe('Air Force Housing Scorecards', () => {
  test('renders the map-led dashboard and scorecard action surface', async ({ page }) => {
    await page.goto('/housing')

    await expect(page.getByRole('heading', { name: 'Housing Supply Health' })).toBeVisible()
    await expect(page.getByRole('img', { name: 'Installation health map' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Generate scorecard' })).toBeVisible()
  })
})
