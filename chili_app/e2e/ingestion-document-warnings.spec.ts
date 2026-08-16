/**
 * Knowledge Bases — per-document warning surfacing (full stack).
 *
 * Uploads a ragged CSV through the real documents pipeline and asserts the
 * worker-persisted parser/extraction warnings reach the Document inventory as
 * a warning chip with visible reasons. No API mocking — the upload round-trips
 * through POST /knowledgebases/{kb}/documents and the Redis-driven worker.
 */
import { test, expect } from '@playwright/test'

import { deleteKnowledgeBase } from './helpers/deleteKb'
import { waitForDocumentWarnings } from './helpers/waitForDocument'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

// Header declares 3 columns; the second data row has 4 fields, which the CSV
// parser reports as a `csv.ragged_row` warning on the parsed document.
const RAGGED_CSV = [
  'claim_id,provider,amount',
  'CLM-2026-00417,Dr. Alice Nguyen,412.00',
  'CLM-2026-00418,Dr. Alice Nguyen,412.00,EXTRA_FIELD',
  '',
].join('\n')

test.describe('Knowledge Bases document warnings', () => {
  test('shows a warning chip with reasons after ingesting a ragged CSV', async ({ page }) => {
    // The default 30s test timeout is what actually failed under a saturated
    // worker (see the pipeline-wait comment below) — the whole test needs
    // headroom, not just the expect() waits.
    test.setTimeout(300_000)
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()

    // Fresh KB so accumulated warnings are deterministic for this spec. The
    // create affordance lives behind <details> now.
    const kbName = `warn-e2e-${Date.now()}`
    await page.locator('details.kb-library__create summary').click()
    await page.getByLabel('Knowledge base name').fill(kbName)
    await page.getByRole('button', { name: 'Create knowledge base' }).click()

    // Creation lands directly in this knowledge base's Add data section.
    await expect(page).toHaveURL(/\/knowledge-bases\/[^/]+\/add$/)
    await expect(page.getByRole('heading', { level: 1, name: kbName })).toBeVisible()
    const kbId = /\/knowledge-bases\/([^/]+)\/add$/.exec(page.url())?.[1]
    if (!kbId) {
      throw new Error(`could not resolve the created knowledge base id from ${page.url()}`)
    }

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

    // KBM-002 unified both source paths behind a single "Run ingestion" CTA;
    // there is no longer a per-source "Submit documents" button.
    const submit = page.getByRole('button', { name: 'Run ingestion' })
    await expect(submit).toBeEnabled()
    // dispatchEvent: the adjacent submit panel overlaps this button at the
    // default e2e viewport, intercepting coordinate clicks.
    await submit.dispatchEvent('click')

    // Wait for the submission's own success signal — a successful submit
    // navigates to Runs — rather than immediately hard-navigating elsewhere.
    // A `page.goto` fired before the upload's XHR resolves would race a
    // still-in-flight request against a full page reload; this is the same
    // proven wait ingestion-truth-safety.spec.ts uses for its submit cases.
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/runs$`), {
      timeout: 60_000,
    })
    // Client-side tab navigation (not page.goto) to Data, so the already-open
    // realtime stream and query cache carry over rather than resetting.
    await page.getByRole('link', { name: 'Data', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/data$`))

    // Confirm the real condition against the API first: warning_count lands
    // as soon as the parse stage finishes, independent of whatever the
    // document's broader lifecycle status is doing (confirmed against the
    // real stack). This fails fast with last_error if ingestion genuinely
    // failed, and is far more diagnosable than a bare DOM timeout under a
    // saturated shared worker.
    await waitForDocumentWarnings(API, kbId, 'ragged-claims.csv')

    // The document list has no polling interval — it refreshes only via the
    // realtime stream's invalidation or a fresh fetch. The API confirmation
    // above already proves the backend is ready; reload for a guaranteed
    // fresh fetch instead of hoping the realtime invalidation has landed too.
    await page.reload()
    const documentRow = page.getByRole('button', { name: /ragged-claims\.csv/ })
    await expect(documentRow).toBeVisible()
    await expect(documentRow.getByText(/\d+ warnings?/)).toBeVisible()

    // Reasons are behind an explicit toggle now: selecting the row used to be
    // the only way in, which nothing on screen said.
    await page.getByRole('button', { name: /^Show \d+ warning/ }).first().click()
    const reasons = page.getByTestId('document-warning-reasons')
    await expect(reasons).toBeVisible()
    await expect(reasons).toContainText('csv.ragged_row')

    await deleteKnowledgeBase(API, kbId)
  })
})
