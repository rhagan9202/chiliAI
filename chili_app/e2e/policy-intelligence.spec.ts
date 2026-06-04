/**
 * Policy Intelligence (full stack, BL-011). The queue is served by the real API
 * from durable, rule-generated policy items (the dev-seed scenario creates one
 * open item targeting the seeded claim). Replaces the retired policy-gap surface.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Policy Intelligence', () => {
  test('renders the rule-generated policy item queue from the real API', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/policy?kb=${kb}`)

    await expect(page.getByRole('heading', { name: 'Policy Intelligence' })).toBeVisible()
    await expect(
      page.getByText('Claim claim-1 exceeds the billing threshold').first(),
    ).toBeVisible()
  })
})
