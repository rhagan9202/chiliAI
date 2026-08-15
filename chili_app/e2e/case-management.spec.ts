/**
 * Case Management (full stack, BL-010). The seeded case is served by the real
 * durable cases repository, KB-scoped. We assert on seed-stable properties
 * (title, priority) rather than status, since other specs in the suite mutate
 * the shared case's status.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Case Management', () => {
  test('renders the seeded case queue and detail', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/cases?kb=${kb}`)

    await expect(page.getByRole('heading', { name: 'Case Management' })).toBeVisible()

    // Select the seeded case by name rather than trusting the auto-selection:
    // earlier specs promote alerts into new cases, any of which may sort ahead
    // of it in the queue.
    await page.getByRole('button', { name: /Redwood DME escalation/ }).first().click()

    // The detail panel shows that case's seed-stable priority plus its actions.
    const detailPanel = page.locator('.case-layout')
    await expect(
      detailPanel
        .locator('.status-pill:not(.status-pill--compact)')
        .and(page.getByLabel('Case priority: high')),
    ).toBeVisible()
    await expect(page.getByRole('button', { name: 'Mark in review' })).toBeVisible()
  })
})
