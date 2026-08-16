/**
 * Knowledge base manager (full stack).
 * The deterministically seeded KB (POST /admin/dev-seed) appears in the manager.
 */

import { test, expect } from '@playwright/test'

test.describe('Knowledge base manager', () => {
  test('the seeded knowledge base appears', async ({ page }) => {
    await page.goto('/knowledge-bases')

    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()
    // Scoped to the list card: the top bar's knowledge-base picker carries the
    // same name in a hidden <option>, which an unscoped match resolves first.
    // The card itself is a link to the knowledge base's workspace, not a
    // selection button.
    await expect(
      page
        .getByRole('region', { name: 'Choose a knowledge base' })
        .getByRole('link', { name: /E2E Seed KB/ })
        .first(),
    ).toBeVisible()
  })
})
