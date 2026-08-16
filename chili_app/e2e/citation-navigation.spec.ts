import { expect, test } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Citation navigation', () => {
  test('opens a document citation from cockpit evidence in the source preview', async ({ page }) => {
    const {
      alert_id: alert,
      entity_id: entity,
      evidence_pack_id: evidence,
      knowledge_base_id: kb,
    } = seeded()

    await page.goto(`/investigation/${entity}?kb=${kb}&alert=${alert}&evidence=${evidence}`)
    await page.getByRole('button', { name: 'View cockpit evidence' }).click()
    await expect(page.getByTestId('evidence-pack-viewer')).toBeVisible()

    const documentReference = page
      .locator('details.evidence-pack__provenance-item')
      .filter({ hasText: 'Seed source document' })
      .first()
    await documentReference.locator('summary').click()

    const sourceLink = documentReference.getByRole('link', {
      name: /open citation source seed source document/i,
    })
    await expect(sourceLink).toHaveAttribute(
      'href',
      `/knowledge-bases/${kb}/data?document=dev-seed-source`,
    )
    await sourceLink.click()

    await expect(page).toHaveURL(
      new RegExp(`/knowledge-bases/${kb}/data\\?document=dev-seed-source`),
    )
    await expect(page.getByText('Document preview', { exact: true })).toBeVisible()
    await expect(page.getByText(/Redwood DME Group claim review/)).toBeVisible()
    await expect(page.getByText(/3 lines from dev-seed-source\.txt/)).toBeVisible()
  })
})
