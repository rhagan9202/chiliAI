/**
 * Policy triage + escalate (full stack, BL-011). The dev-seed scenario creates
 * one open policy item; this spec triages it via the real /policy/items/{id}/triage
 * endpoint and asserts the status flips. Escalate additionally creates a case.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Policy triage', () => {
  test('escalating the seeded policy item creates a case via the real API', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/policy?kb=${kb}`)

    await expect(page.getByRole('heading', { name: 'Policy Intelligence' })).toBeVisible()

    // `exact: true` so this targets the triage action button and NOT the
    // "Escalated" status-filter chip (getByRole name matching is substring).
    const escalate = page.getByRole('button', { name: 'Escalate', exact: true })
    await expect(escalate).toBeVisible()

    // Wait for the real triage POST to land so the case is persisted before we
    // navigate away.
    const [response] = await Promise.all([
      page.waitForResponse(
        (r) =>
          /\/policy\/items\/.+\/triage/.test(r.url()) && r.request().method() === 'POST',
      ),
      escalate.click(),
    ])
    expect(response.ok()).toBeTruthy()

    // The escalation created a case, visible KB-scoped on the Cases page.
    await page.goto(`/cases?kb=${kb}`)
    await expect(page.getByText(/Policy escalation:/).first()).toBeVisible()
  })
})
