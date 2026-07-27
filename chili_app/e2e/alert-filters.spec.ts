/**
 * Combinable triage filters (UXA-401), against the real feed.
 *
 * The old chip row was single-select and conflated severity with status, so
 * "critical AND unacknowledged" — the product's most common triage filter —
 * could not be expressed at all.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Alert Feed filters', () => {
  test('combines severity and status, and survives a reload by URL', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    await expect(page.getByRole('group', { name: 'Severity' })).toBeVisible()
    await expect(page.getByRole('group', { name: 'Status' })).toBeVisible()

    await page.getByRole('button', { name: /^Critical, \d+ matching$/ }).click()
    await page.getByRole('button', { name: /^Open, \d+ matching$/ }).click()

    await expect(page).toHaveURL(/severity=critical/)
    await expect(page).toHaveURL(/status=open/)
    // The knowledge base scope is not this model's parameter and must survive.
    await expect(page).toHaveURL(new RegExp(`kb=${kb}`))
    await expect(page.locator('.alert-row-card')).toHaveCount(1)

    await page.reload()
    await expect(page.locator('.alert-row-card')).toHaveCount(1)
    await expect(page.getByRole('button', { name: /^Critical, \d+ matching$/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  test('a filter that matches nothing says so and offers a way back', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()

    // The seeded alert is critical, so Low can only be empty.
    await page.goto(`/alerts?kb=${kb}&severity=low`)

    await expect(page.locator('.alert-row-card')).toHaveCount(0)
    await expect(page.getByText(/^Showing 0 of/)).toBeVisible()

    await page.getByRole('button', { name: 'Clear filters' }).click()
    await expect(page.locator('.alert-row-card').first()).toBeVisible()
  })

  test('search narrows the queue by entity and by finding', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()

    await page.goto(`/alerts?kb=${kb}&q=redwood`)
    await expect(page.locator('.alert-row-card')).toHaveCount(1)

    await page.goto(`/alerts?kb=${kb}&q=no-such-subject`)
    await expect(page.locator('.alert-row-card')).toHaveCount(0)
  })
})
