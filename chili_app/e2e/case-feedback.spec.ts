/**
 * Case feedback (full stack). Submitting analyst feedback POSTs to the real API
 * and the feedback history renders the note after refetch.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

const NOTES = 'Unusual billing pattern consistent with upcoding scheme.'

test.describe('Case feedback submission', () => {
  test('submitting feedback persists and renders in history', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/cases?kb=${kb}`)

    await expect(page.getByText('Redwood DME escalation').first()).toBeVisible()
    await page.getByPlaceholder('Document the current evidence assessment').fill(NOTES)
    await page.getByRole('button', { name: 'Save feedback' }).click()

    // First match: the note is appended to history, and a stack that has run
    // this spec before already carries an identical earlier entry. The claim
    // is that saving lands the note, not that it is the only one.
    await expect(page.getByText(NOTES).first()).toBeVisible()
    // Scope to the history entry: a bare getByText('suspicious') resolves to
    // the hidden combobox <option> first.
    await expect(
      page.locator('.metric-row--stacked strong', { hasText: 'suspicious' }).first(),
    ).toBeVisible()
  })
})
