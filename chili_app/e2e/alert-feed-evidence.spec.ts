/**
 * Alert Feed evidence viewer (full stack, BL-006 + U2 reshape). The triage row
 * leads with the risk numeral and flag label; "View evidence" fetches the real
 * evidence pack and renders the narrative-lead EvidencePackViewer.
 */
import { test, expect } from '@playwright/test'

test.describe('Alert Feed evidence viewer', () => {
  test('triage row leads with numeral and View evidence renders the narrative band', async ({
    page,
  }) => {
    await page.goto('/alerts')
    await expect(page.getByText('Redwood DME Group').first()).toBeVisible()

    // U2 triage treatment: numeral = round(confidence*100), mono flag label
    // from the alert's own tags.
    await expect(page.getByTestId('triage-numeral').first()).toHaveText('96')
    await expect(page.getByText('BILLING · PEER-DEVIATION').first()).toBeVisible()

    await page.getByRole('button', { name: 'View evidence' }).first().click()

    // The reshaped viewer leads with the AI narrative band; the pack's
    // reasoning renders inside it.
    await expect(page.getByTestId('evidence-narrative')).toBeVisible()
    await expect(page.getByText('◆ AI NARRATIVE')).toBeVisible()
    await expect(
      page.getByText('Provider billing concentration and upcoding indicate elevated fraud risk.'),
    ).toBeVisible()
    await expect(page.getByText('confidence 82%')).toBeVisible()
  })
})
