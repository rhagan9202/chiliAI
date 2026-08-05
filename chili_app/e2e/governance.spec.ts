/**
 * Governance dashboard (full stack, SAFE-CMS-020). The page reads the real
 * KB-scoped governance report endpoint; no route or response mocking.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Governance dashboard', () => {
  test('renders release readiness for the seeded knowledge base', async ({ page }) => {
    const kb = seeded().knowledge_base_id

    await page.addInitScript(() => {
      window.localStorage.setItem('chiliai.selectedRole', 'supervisor')
    })

    const reportResponse = page.waitForResponse(
      (response) =>
        response.url().includes(`/knowledgebases/${kb}/governance/report`) &&
        response.request().method() === 'GET',
    )

    await page.goto(`/governance?kb=${kb}`)

    expect((await reportResponse).ok()).toBeTruthy()
    await expect(page.getByRole('heading', { name: 'Governance' })).toBeVisible()
    await expect(page.getByLabel(/Release readiness: (ready|blocked)/)).toBeVisible()
    await expect(page.getByLabel(/Published versions: \d+/)).toBeVisible()
    await expect(page.getByLabel(/Pending approvals: \d+/)).toBeVisible()
    await expect(page.getByLabel(/Challenged explanations: \d+/)).toBeVisible()
    await expect(page.getByRole('region', { name: 'Production versions' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Pending approvals' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Release blockers' })).toBeVisible()
  })
})
