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
      page.getByText('Claim claim-1 payment exceeds the elevated-review threshold').first(),
    ).toBeVisible()
  })

  test('filters the queue server-side by several statuses at once (UXA-401)', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/policy?kb=${kb}`)

    // Counts come from the real response's status_counts, tallied over the KB.
    const open = page.getByRole('button', { name: /^Open, \d+ matching$/ })
    await expect(open).toBeVisible()
    await expect(page.getByText(/Showing all \d+ items?/)).toBeVisible()

    // A status nothing holds empties the queue and offers the way back.
    const [rejectedResponse] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes('/policy/items?') && r.url().includes('status=rejected'),
      ),
      page.getByRole('button', { name: /^Rejected, \d+ matching$/ }).click(),
    ])
    expect(rejectedResponse.ok()).toBeTruthy()
    await expect(page.getByText('No items match these filters')).toBeVisible()

    // Adding "open" to the selection must UNION with it, not replace it: the
    // request carries both values and the seeded open item comes back. A
    // single-value server filter could not answer this.
    const [unionResponse] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes('/policy/items?') &&
          r.url().includes('status=rejected') &&
          r.url().includes('status=open'),
      ),
      open.click(),
    ])
    expect(unionResponse.ok()).toBeTruthy()
    await expect(
      page.getByText('Claim claim-1 payment exceeds the elevated-review threshold').first(),
    ).toBeVisible()

    // The filter is in the URL, so it survives a reload and is shareable.
    await page.reload()
    await expect(page.getByRole('button', { name: /^Open, \d+ matching$/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(page.getByRole('button', { name: /^Rejected, \d+ matching$/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    await page.getByRole('button', { name: 'Clear filters' }).first().click()
    await expect(page).toHaveURL(new RegExp(`/policy\\?kb=${kb}$`))
  })
})
