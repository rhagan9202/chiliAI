/**
 * Auth mode (full stack). The e2e stack runs auth-disabled (analyst override),
 * so protected routes render directly without redirecting to /login. (The
 * auth-enabled redirect path is covered by backend auth unit tests.)
 */
import { test, expect } from '@playwright/test'

test.describe('Auth-disabled access', () => {
  test('a protected route renders the app without a login redirect', async ({ page }) => {
    await page.goto('/cases')
    await expect(page).not.toHaveURL(/\/login/)
    await expect(page.locator('aside[aria-label="Primary navigation"]')).toBeVisible()
  })
})
