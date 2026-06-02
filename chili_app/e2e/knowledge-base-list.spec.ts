/**
 * Knowledge base manager (full stack).
 * The deterministically seeded KB (POST /admin/dev-seed) appears in the manager.
 */

import { test, expect } from '@playwright/test'

test.describe('Knowledge base manager', () => {
  test('the seeded knowledge base appears', async ({ page }) => {
    await page.goto('/knowledge-bases')

    await expect(page.getByRole('heading', { name: 'Ingestion Studio' })).toBeVisible()
    await expect(page.getByText('E2E Seed KB').first()).toBeVisible()
  })
})
