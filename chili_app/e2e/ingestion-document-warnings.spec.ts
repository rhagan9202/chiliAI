/**
 * Ingestion Studio — per-document warning surfacing (full stack).
 *
 * Uploads a ragged CSV through the real documents pipeline and asserts the
 * worker-persisted parser/extraction warnings reach the Document inventory as
 * a warning chip with visible reasons. No API mocking — the upload round-trips
 * through POST /knowledgebases/{kb}/documents and the Redis-driven worker.
 */
import { test, expect } from '@playwright/test'

// Header declares 3 columns; the second data row has 4 fields, which the CSV
// parser reports as a `csv.ragged_row` warning on the parsed document.
const RAGGED_CSV = [
  'claim_id,provider,amount',
  'CLM-2026-00417,Dr. Alice Nguyen,412.00',
  'CLM-2026-00418,Dr. Alice Nguyen,412.00,EXTRA_FIELD',
  '',
].join('\n')

test.describe('Ingestion Studio document warnings', () => {
  test('shows a warning chip with reasons after ingesting a ragged CSV', async ({ page }) => {
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Ingestion Studio' })).toBeVisible()

    // Fresh KB so accumulated warnings are deterministic for this spec.
    // Creation auto-selects the KB and advances the wizard to the source step.
    const kbName = `warn-e2e-${Date.now()}`
    await page.getByLabel('Knowledge base name').fill(kbName)
    await page.getByRole('button', { name: 'Create knowledge base' }).click()
    await expect(page.getByText(kbName).first()).toBeVisible()

    await page
      .locator('label.ingestion-source-choice__option', { hasText: 'Documents' })
      .first()
      .click()

    await page.getByLabel('Document files').setInputFiles({
      name: 'ragged-claims.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(RAGGED_CSV, 'utf-8'),
    })

    const submit = page.getByRole('button', { name: 'Submit documents' })
    await expect(submit).toBeEnabled()
    await submit.click()

    // The worker parses the CSV and persists the ragged-row warning; the
    // documents query refreshes via SSE/polling. Allow the pipeline time.
    const documentRow = page.getByRole('button', { name: /ragged-claims\.csv/ })
    await expect(documentRow).toBeVisible({ timeout: 30_000 })
    await expect(documentRow.getByText(/\d+ warnings?/)).toBeVisible({ timeout: 30_000 })

    // Selecting the document reveals the persisted reasons.
    await documentRow.click()
    const reasons = page.getByTestId('document-warning-reasons')
    await expect(reasons).toBeVisible()
    await expect(reasons).toContainText('csv.ragged_row')
  })
})
