/**
 * Smoke (full stack, auth-disabled e2e). The app loads and renders the shell
 * for the anonymous analyst (CHILI_DEV_ANONYMOUS_ROLE), not a login page.
 */
import { test, expect } from '@playwright/test'

test.describe('Smoke', () => {
  test('root renders the app shell (auth disabled)', async ({ page }) => {
    await page.goto('/')
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('aside[aria-label="Primary navigation"]')).toBeVisible()
  })
})
