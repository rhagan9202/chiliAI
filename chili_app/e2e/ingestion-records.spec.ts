/**
 * Ingestion Studio — structured records flow (full stack, BL-013).
 *
 * Drives the records source path end-to-end against the real API/worker:
 * pick the Structured Records source, select the config-defined
 * `carrier_claims_a` file_upload feed (medicare_fraud_cms_desynpuf domain),
 * upload a tiny inline CSV, let it auto-parse, submit, and assert a success
 * receipt lands in the run timeline. No API mocking — the multipart upload
 * round-trips through POST /records/{kb}/files into the real records pipeline.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

// Matches the `carrier_claims_a` feed schema: required DESYNPUF_ID + CLM_ID,
// optional dates (ISO YYYY-MM-DD), performing-physician NPI, line payment.
const CARRIER_CLAIMS_CSV = [
  'DESYNPUF_ID,CLM_ID,CLM_FROM_DT,CLM_THRU_DT,PRF_PHYSN_NPI_1,LINE_NCH_PMT_AMT_1',
  '00013D2EFD8E45D1,887234567890001,2009-01-12,2009-01-12,1234567893,125.50',
  '00016F745862898F,887234567890002,2009-02-03,2009-02-04,1987654320,84.00',
  '',
].join('\n')

test.describe('Ingestion Studio records flow', () => {
  test('uploads a CSV through the carrier_claims_a feed and shows a success receipt', async ({
    page,
  }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/knowledge-bases?kb=${kb}`)

    await expect(page.getByRole('heading', { name: 'Ingestion Studio' })).toBeVisible()

    // Choose the structured records source.
    await page.getByRole('radio', { name: /Structured Records/i }).check()

    // Select the config-defined file_upload feed.
    await page.getByLabel('Records feed').selectOption('carrier_claims_a')

    // Upload the inline CSV; file_upload feeds auto-parse on selection.
    await page.getByLabel('Records file').setInputFiles({
      name: 'carrier_claims_a.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(CARRIER_CLAIMS_CSV, 'utf-8'),
    })

    // Auto-parse completes and the preview is ready.
    await expect(page.getByText('Parsed for preview')).toBeVisible()

    const submit = page.getByRole('button', { name: 'Submit records' })
    await expect(submit).toBeEnabled()
    await submit.click()

    // A success receipt for the feed appears in the run timeline (the run list
    // is labelled "Ingestion runs").
    const timeline = page.getByRole('list', { name: /ingestion runs/i })
    await expect(
      timeline.getByText(/records accepted for carrier_claims_a\./i),
    ).toBeVisible()
    // The receipt carries an "accepted" status chip plus the counts summary.
    await expect(timeline.getByText(/\d+ accepted, \d+ duplicate, \d+ rejected/)).toBeVisible()
  })
})
