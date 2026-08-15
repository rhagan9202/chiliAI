/**
 * Knowledge Bases — phase-1 truth-and-safety regressions (full stack).
 *
 * Every assertion here corresponds to a way the page used to mislead or
 * destroy work: unclickable-but-undimmed controls, a file picker that
 * discarded prior staging, a receipt log that lived only in the submitting
 * tab, a document that produced nothing reading as "ready", and two deletions
 * that fired on the first click. No API mocking — the whole spec drives the
 * real API, worker and stores.
 *
 * Serial: the scenarios share one knowledge base created by the first step,
 * and the last one deletes it.
 */
import { readFileSync } from 'node:fs'

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

const FIXTURES = '../docs/testing/knowledge_base_fixtures/medicare_fraud'
const SINGLE_CLAIM = readFileSync(`${FIXTURES}/01_single_claim_complete.json`)
const ZERO_ENTITY = readFileSync(`${FIXTURES}/06_zero_entity_resume_like.txt`)

// Matches the `carrier_claims_a` feed schema of the medicare_fraud_cms_desynpuf
// pack. CLM_IDs are unique per run: rows dedupe on (kb, record_type, id), and
// an all-duplicate submission starts no workflow at all.
const RUN_SUFFIX = String(Date.now() % 1_000_000).padStart(6, '0')
const CARRIER_CLAIMS_CSV = [
  'DESYNPUF_ID,CLM_ID,CLM_FROM_DT,CLM_THRU_DT,PRF_PHYSN_NPI_1,LINE_NCH_PMT_AMT_1',
  `00013D2EFD8E45D1,997234001${RUN_SUFFIX},2009-01-12,2009-01-12,1234567893,125.50`,
  '',
].join('\n')

const kbName = `truth-safety-e2e-${Date.now()}`
const otherKbName = `${kbName}-other`

/** The KB list card. The top-bar picker also carries every KB name, in hidden
 *  <option> elements, so name assertions have to be scoped to this region. */
function kbList(page: Page) {
  return page.getByRole('region', { name: 'Choose a knowledge base' })
}

/** Click the source-type option: the radio is visually hidden inside its label. */
async function chooseSource(page: Page, label: 'Documents' | 'Structured Records') {
  await page
    .locator('label.ingestion-source-choice__option', { hasText: label })
    .first()
    .dispatchEvent('click')
}

async function selectKnowledgeBase(page: Page, name: string) {
  await kbList(page)
    .getByRole('button', { name: new RegExp(name) })
    .first()
    .dispatchEvent('click')
}

test.describe.configure({ mode: 'serial' })

test.describe('Knowledge Bases truth and safety', () => {
  test.beforeEach(async ({ page }) => {
    // The document pipeline runs on a shared worker that may be saturated by
    // another spec's KB; the whole test needs headroom, not just its waits.
    test.setTimeout(300_000)
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()
  })

  test('a disabled primary action looks disabled and names what is missing', async ({ page }) => {
    await page.getByLabel('Knowledge base name').fill(kbName)
    await page.getByRole('button', { name: 'Create knowledge base' }).click()
    await expect(kbList(page).getByText(kbName).first()).toBeVisible()

    const run = page.getByRole('button', { name: 'Run ingestion' })
    await expect(run).toBeDisabled()
    // The chip is this control's disabled-reason text.
    await expect(page.getByText('Select source type')).toBeVisible()
    // Disabled means dimmed and unclickable, not merely inert.
    await expect(run).toHaveCSS('cursor', 'not-allowed')
    expect(Number(await run.evaluate((el) => getComputedStyle(el).opacity))).toBeLessThan(1)
  })

  test('staging appends, removes one file at a time, and survives a re-pick', async ({ page }) => {
    await selectKnowledgeBase(page, kbName)
    await chooseSource(page, 'Documents')

    // Exact: the staged-files list is labelled "Selected document files",
    // which a substring match also picks up once staging is non-empty.
    const input = page.getByLabel('Document files', { exact: true })
    await input.setInputFiles({
      name: '01_single_claim_complete.json',
      mimeType: 'application/json',
      buffer: SINGLE_CLAIM,
    })
    // A second pick used to discard the first silently.
    await input.setInputFiles({
      name: '06_zero_entity_resume_like.txt',
      mimeType: 'text/plain',
      buffer: ZERO_ENTITY,
    })

    const staged = page.getByRole('list', { name: 'Selected document files' })
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toBeVisible()
    await expect(staged.getByText('06_zero_entity_resume_like.txt', { exact: true })).toBeVisible()

    await staged.getByRole('button', { name: /Remove 01_single_claim_complete\.json/ }).click()
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toHaveCount(0)
    await expect(staged.getByText('06_zero_entity_resume_like.txt', { exact: true })).toBeVisible()

    // Re-picking the removed file must fire a change event even though the
    // input already held that filename once.
    await input.setInputFiles({
      name: '01_single_claim_complete.json',
      mimeType: 'application/json',
      buffer: SINGLE_CLAIM,
    })
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toBeVisible()
  })

  test('a staged draft belongs to its knowledge base and never crosses to another', async ({
    page,
  }) => {
    await selectKnowledgeBase(page, kbName)
    await chooseSource(page, 'Documents')
    await page.getByLabel('Document files', { exact: true }).setInputFiles({
      name: '01_single_claim_complete.json',
      mimeType: 'application/json',
      buffer: SINGLE_CLAIM,
    })

    const staged = page.getByRole('list', { name: 'Selected document files' })
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toBeVisible()

    await page.getByLabel('Knowledge base name').fill(otherKbName)
    await page.getByRole('button', { name: 'Create knowledge base' }).click()
    await expect(kbList(page).getByText(otherKbName).first()).toBeVisible()

    // The new knowledge base starts empty — this is the leak that let files
    // staged for one corpus submit into another.
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toHaveCount(0)

    await selectKnowledgeBase(page, kbName)
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toBeVisible()
  })

  test('a submitted run and its receipt survive a page reload', async ({ page }) => {
    await selectKnowledgeBase(page, kbName)
    await chooseSource(page, 'Documents')
    const input = page.getByLabel('Document files', { exact: true })
    await input.setInputFiles({
      name: '01_single_claim_complete.json',
      mimeType: 'application/json',
      buffer: SINGLE_CLAIM,
    })
    await input.setInputFiles({
      name: '06_zero_entity_resume_like.txt',
      mimeType: 'text/plain',
      buffer: ZERO_ENTITY,
    })

    const submit = page.getByRole('button', { name: 'Run ingestion' })
    await expect(submit).toBeEnabled()
    await submit.dispatchEvent('click')

    // A submission that succeeded belongs to the server now: the draft clears.
    await expect(page.getByRole('list', { name: 'Selected document files' })).toHaveCount(0, {
      timeout: 60_000,
    })

    const timeline = page.getByRole('list', { name: /ingestion runs/i })
    await expect(timeline.getByText('ingestion', { exact: true }).first()).toBeVisible({
      timeout: 120_000,
    })
    const before = await timeline.getByRole('listitem').count()

    await page.reload()
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()
    await selectKnowledgeBase(page, kbName)
    // Runs used to be a client-side log: a reload erased them.
    await expect(timeline.getByRole('listitem')).toHaveCount(before, { timeout: 60_000 })
  })

  test('the inventory tells the truth about a document that produced no entities', async ({
    page,
  }) => {
    await selectKnowledgeBase(page, kbName)

    const zeroEntityRow = page.getByRole('button', { name: /06_zero_entity_resume_like\.txt/ })
    await expect(zeroEntityRow).toBeVisible({ timeout: 120_000 })
    // Used to render a green "ready" chip for a document that contributed nothing.
    await expect(zeroEntityRow.getByText('No entities')).toBeVisible({ timeout: 120_000 })

    await page.getByLabel('Filter documents by status').selectOption('extracted_empty')
    const rows = page.locator('.knowledge-base-document-row')
    await expect(rows).toHaveCount(1, { timeout: 30_000 })
    await expect(rows.first()).toContainText('06_zero_entity_resume_like.txt')

    await page.getByLabel('Filter documents by status').selectOption('all')
    await expect(rows.first()).toBeVisible()
  })

  test('a records submission reports its counts from the server', async ({ page }) => {
    await selectKnowledgeBase(page, kbName)
    await chooseSource(page, 'Structured Records')
    await page.getByLabel('Records feed').selectOption('carrier_claims_a')
    await page.getByLabel('Records file').setInputFiles({
      name: 'carrier_claims_a.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(CARRIER_CLAIMS_CSV, 'utf-8'),
    })
    await expect(page.getByText('Parsed for preview')).toBeVisible()

    const submit = page.getByRole('button', { name: 'Run ingestion' })
    await expect(submit).toBeEnabled()
    await submit.dispatchEvent('click')

    const timeline = page.getByRole('list', { name: /ingestion runs/i })
    const counts = timeline.getByText(/\d+ accepted, \d+ duplicate, \d+ rejected/)
    await expect(counts.first()).toBeVisible({ timeout: 120_000 })

    // The counts come from the run, not from this tab: they survive a reload.
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()
    await selectKnowledgeBase(page, kbName)
    await expect(counts.first()).toBeVisible({ timeout: 60_000 })
  })

  test('both deletions require confirmation, and the knowledge base one requires its name', async ({
    page,
  }) => {
    await selectKnowledgeBase(page, kbName)

    // Removing a document: a plain confirmation that can be cancelled.
    const documentRow = page.getByRole('button', { name: /06_zero_entity_resume_like\.txt/ })
    await expect(documentRow).toBeVisible({ timeout: 60_000 })
    await documentRow.click()
    await page.getByRole('button', { name: 'Remove document' }).first().dispatchEvent('click')
    const removeDialog = page.getByRole('dialog')
    await expect(removeDialog).toContainText('06_zero_entity_resume_like.txt')
    await removeDialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(documentRow).toBeVisible()

    // Deleting the whole corpus: typed-name confirmation stating the radius.
    await page
      .getByRole('button', { name: 'Delete selected knowledge base' })
      .dispatchEvent('click')
    const deleteDialog = page.getByRole('dialog')
    await expect(deleteDialog).toContainText('cannot be undone')
    const confirm = deleteDialog.getByRole('button', { name: 'Delete knowledge base' })
    await expect(confirm).toBeDisabled()

    await deleteDialog.getByRole('textbox').fill(kbName)
    await expect(confirm).toBeEnabled()
    await confirm.click()

    await expect(kbList(page).getByText(kbName, { exact: true })).toHaveCount(0, {
      timeout: 60_000,
    })
  })
})
