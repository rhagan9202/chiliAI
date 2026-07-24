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
    // The default 30s test timeout is what actually failed under a saturated
    // worker (see the pipeline-wait comment below) — the whole test needs
    // headroom, not just the expect() waits.
    test.setTimeout(300_000)
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Ingestion Studio' })).toBeVisible()

    // Fresh KB so accumulated warnings are deterministic for this spec.
    // Creation auto-selects the KB and advances the wizard to the source step.
    const kbName = `warn-e2e-${Date.now()}`
    await page.getByLabel('Knowledge base name').fill(kbName)
    await page.getByRole('button', { name: 'Create knowledge base' }).click()
    await expect(page.getByText(kbName).first()).toBeVisible()

    // dispatchEvent instead of a coordinate click: the KB-created toast can
    // overlay the option, and label activation forwards the click to the
    // visually-hidden radio regardless of hit-testing.
    await page
      .locator('label.ingestion-source-choice__option', { hasText: 'Documents' })
      .first()
      .dispatchEvent('click')
    await expect(page.getByRole('radio', { name: /^Documents/ })).toBeChecked()

    await page.getByLabel('Document files').setInputFiles({
      name: 'ragged-claims.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(RAGGED_CSV, 'utf-8'),
    })

    const submit = page.getByRole('button', { name: 'Submit documents' })
    await expect(submit).toBeEnabled()
    // dispatchEvent: the adjacent submit panel overlaps this button at the
    // default e2e viewport, intercepting coordinate clicks.
    await submit.dispatchEvent('click')

    // The worker parses the CSV and persists the ragged-row warning; the
    // documents query refreshes via SSE/polling. Budget for a saturated
    // worker: on a stack that just ran `make demo-cms`, this parse event
    // queues behind the demo KB's per-document Flow B passes (full-KB GNN
    // snapshots, minutes each), so 30s flakes while 120s holds.
    const documentRow = page.getByRole('button', { name: /ragged-claims\.csv/ })
    await expect(documentRow).toBeVisible({ timeout: 120_000 })
    await expect(documentRow.getByText(/\d+ warnings?/)).toBeVisible({ timeout: 120_000 })

    // Selecting the document reveals the persisted reasons.
    await documentRow.click()
    const reasons = page.getByTestId('document-warning-reasons')
    await expect(reasons).toBeVisible()
    await expect(reasons).toContainText('csv.ragged_row')
  })
})
