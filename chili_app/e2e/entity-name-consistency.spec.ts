/**
 * One entity, one name (UXA-304). Clicking "Investigate <name>" on the alert
 * feed used to land on a page titled by a different field entirely — the alert
 * carried a label written when it fired, while the workbench resolved its own
 * from the graph. Both now resolve through `ui.display_fields`, so this asserts
 * they agree against the live stack rather than against a fixture.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Entity naming', () => {
  test('the alert card name is the workbench title after click-through', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    const card = page.locator('.alert-row-card__title').first()
    await expect(card).toBeVisible()
    const nameOnCard = (await card.innerText()).trim()
    expect(nameOnCard.length).toBeGreaterThan(0)

    await page.getByRole('link', { name: `Investigate ${nameOnCard}` }).first().click()

    await expect(page.getByRole('heading', { level: 1, name: nameOnCard })).toBeVisible()
  })

  test('the AI rail names its context instead of showing an identifier', async ({ page }) => {
    const { knowledge_base_id: kb, alert_id: alertId } = seeded()
    await page.goto(`/alerts?kb=${kb}&alert=${alertId}`)

    const rail = page.getByLabel('AI investigator assistant')
    await expect(rail).toBeVisible()
    await expect(rail).not.toContainText(alertId)
  })
})
