/**
 * Bulk triage against the real API (UXA-406).
 *
 * Every alert had to be acknowledged one at a time. This selects what the
 * current filter shows, acknowledges it in one action, and asserts the change
 * persisted server-side rather than only in the DOM.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

test.describe('Bulk triage', () => {
  test('selecting the filtered set and acknowledging it persists via the API', async ({ page }) => {
    const { knowledge_base_id: kb, alert_id: alertId } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    await page.getByRole('checkbox', { name: 'Select all alerts in view' }).check()
    await expect(page.getByText(/\d+ alerts? selected/)).toBeVisible()

    await page.getByRole('button', { name: /^Acknowledge \d+ alerts?$/ }).click()

    const dialog = page.getByRole('dialog')
    // The confirmation must state the exact count it is about to affect.
    await expect(dialog).toContainText(/This marks \d+ alerts? as seen/)
    await dialog.getByRole('button', { name: 'Acknowledge' }).click()

    await expect
      .poll(async () => {
        const response = await fetch(`${API}/alerts/${alertId}`)
        const payload = (await response.json()) as { alert: { status: string } }
        return payload.alert.status
      })
      .toBe('acknowledged')
  })

  test('a selection is dropped when a filter takes it out of view', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    await page.getByRole('checkbox', { name: 'Select all alerts in view' }).check()
    await expect(page.getByText(/\d+ alerts? selected/)).toBeVisible()

    // The seeded alert is critical, so Low can only be empty.
    await page.getByRole('button', { name: /^Low, \d+ matching$/ }).click()

    await expect(page.getByText(/\d+ alerts? selected/)).toBeHidden()
  })

  test('selection is reachable by keyboard', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    const selectAll = page.getByRole('checkbox', { name: 'Select all alerts in view' })
    await selectAll.focus()
    await page.keyboard.press('Space')

    await expect(selectAll).toBeChecked()
    await expect(page.getByText(/\d+ alerts? selected/)).toBeVisible()
  })
})
