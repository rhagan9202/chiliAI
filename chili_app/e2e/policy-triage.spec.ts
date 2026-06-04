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

    await expect(page.getByText('Policy Intelligence')).toBeVisible()
    const escalate = page.getByRole('button', { name: 'Escalate' }).first()
    await expect(escalate).toBeVisible()
    await escalate.click()

    // The detail panel reflects the escalated status from the real backend.
    await expect(page.getByText('escalated')).toBeVisible()

    // The escalation created a case, visible KB-scoped on the Cases page.
    await page.goto(`/cases?kb=${kb}`)
    await expect(page.getByText(/Policy escalation:/)).toBeVisible()
  })
})
