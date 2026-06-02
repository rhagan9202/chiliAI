/**
 * App shell (full stack). The sidebar nav + topbar render for the real
 * anonymous-analyst session (real /auth/me, real /config/domain). We assert on
 * nav labels that are stable across the config-load boundary and present for
 * the analyst role: "Alert Feed" and "Knowledge Bases".
 */
import { test, expect } from '@playwright/test'

test.describe('App shell', () => {
  test('config-driven sidebar nav renders', async ({ page }) => {
    await page.goto('/alerts')
    const sidebar = page.locator('aside[aria-label="Primary navigation"]')
    await expect(sidebar).toBeVisible()
    await expect(sidebar.getByText('Alert Feed').first()).toBeVisible()
    await expect(sidebar.getByText('Knowledge Bases').first()).toBeVisible()
  })
})
