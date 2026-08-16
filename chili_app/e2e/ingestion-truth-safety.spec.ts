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
 * Serial: the scenarios share one knowledge base created by the first step;
 * the last test deletes it via the UI, and `afterAll` deletes it too if an
 * earlier test failed (a serial failure skips the rest, including that last
 * test). A second knowledge base is created for the cross-KB isolation case
 * and is always cleaned up in `afterAll`.
 */
import { readFileSync } from 'node:fs'

import { test, expect } from '@playwright/test'
import type { Page } from '@playwright/test'

import { deleteKnowledgeBase } from './helpers/deleteKb'
import { waitForDocumentStatus } from './helpers/waitForDocument'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

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

/** Id of the knowledge base created by the first test; every later test reads it. */
let kbId = ''
/** Set once the final test's own UI deletion of `kbId` succeeds, so `afterAll`
 *  does not also try to delete an already-deleted knowledge base. */
let kbDeleted = false
/** Id of the second knowledge base created for the cross-KB isolation case. */
let otherKbId: string | null = null

/** The KB library card list. The top-bar picker also carries every KB name, in
 *  hidden <option> elements, so name assertions have to be scoped to this region. */
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

test.describe.configure({ mode: 'serial' })

test.describe('Knowledge Bases truth and safety', () => {
  // The document pipeline runs on a shared worker that may be saturated by
  // another spec's KB; every test in this file needs headroom, not just its
  // own inner waits — this used to live on a shared `beforeEach` that every
  // test inherited, and has to keep covering all of them, not just the ones
  // that happen to touch a large upload.
  test.beforeEach(() => {
    test.setTimeout(300_000)
  })

  test.afterAll(async () => {
    // A failure earlier in this serial file skips the final (deleting) test,
    // which is otherwise the only place `kbId` gets cleaned up.
    if (kbId && !kbDeleted) {
      await deleteKnowledgeBase(API, kbId)
    }
    if (otherKbId) {
      await deleteKnowledgeBase(API, otherKbId)
    }
  })

  test('a disabled primary action looks disabled and names what is missing', async ({ page }) => {
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()

    // The create affordance lives behind <details> now — rarer than browsing.
    await page.locator('details.kb-library__create summary').click()
    await page.getByLabel('Knowledge base name').fill(kbName)
    await page.getByRole('button', { name: 'Create knowledge base' }).click()

    // A brand-new corpus has nothing to look at anywhere else, so creation
    // lands directly in its Add data workspace — capture the id from there.
    await expect(page).toHaveURL(/\/knowledge-bases\/[^/]+\/add$/)
    kbId = /\/knowledge-bases\/([^/]+)\/add$/.exec(page.url())?.[1] ?? ''
    expect(kbId, 'the created knowledge base id must be resolvable from the URL').toBeTruthy()
    await expect(page.getByRole('heading', { level: 1, name: kbName })).toBeVisible()

    const run = page.getByRole('button', { name: 'Run ingestion' })
    await expect(run).toBeDisabled()
    // The chip is this control's disabled-reason text.
    await expect(page.getByText('Select source type')).toBeVisible()
    // Disabled means dimmed and unclickable, not merely inert.
    await expect(run).toHaveCSS('cursor', 'not-allowed')
    expect(Number(await run.evaluate((el) => getComputedStyle(el).opacity))).toBeLessThan(1)
  })

  test('staging appends, removes one file at a time, and survives a re-pick', async ({ page }) => {
    await page.goto(`/knowledge-bases/${kbId}/add`)
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
    request,
  }) => {
    // Created directly through the API: this case is about draft isolation,
    // not the create flow (already covered above), and creating it up front
    // means kb1's own /add is never mid-stage while we go make a second KB.
    const createRes = await request.post(`${API}/knowledgebases`, {
      data: { name: otherKbName, description: 'cross-kb isolation e2e' },
    })
    expect(createRes.ok(), 'creating the second knowledge base must succeed').toBeTruthy()
    otherKbId = ((await createRes.json()) as { id: string }).id

    await page.goto(`/knowledge-bases/${kbId}/add`)
    await chooseSource(page, 'Documents')
    await page.getByLabel('Document files', { exact: true }).setInputFiles({
      name: '01_single_claim_complete.json',
      mimeType: 'application/json',
      buffer: SINGLE_CLAIM,
    })

    const staged = page.getByRole('list', { name: 'Selected document files' })
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toBeVisible()

    const picker = page.getByLabel('Active knowledge base')
    const discardDialog = page.getByRole('dialog', { name: /discard staged files/i })

    // Switching knowledge bases mid-stage is a real in-app navigation, and the
    // workspace guards it exactly like any other departure from Add data: it
    // asks first rather than silently discarding. Cancelling proves nothing
    // is lost by the mere attempt to switch — kb1's draft is untouched.
    await picker.selectOption(otherKbId as string)
    await expect(discardDialog).toBeVisible()
    await discardDialog.getByRole('button', { name: 'Keep staging' }).click()
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/add$`))
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toBeVisible()

    // Now actually cross over: confirming the discard is a *soft*, in-app
    // navigation (the blocker's own `blocker.proceed?.()`), not a hard reload
    // — the JS session and its Zustand store stay alive the whole time. A
    // hard `page.goto` would prove nothing here, because it wipes the entire
    // store (every knowledge base's draft, not just kb1's), so kb2 starting
    // empty would be true under a reintroduced shared-slot bug just as much
    // as under correct per-KB keying. Only a live, in-session crossover can
    // tell those apart.
    await picker.selectOption(otherKbId as string)
    await expect(discardDialog).toBeVisible()
    await discardDialog.getByRole('button', { name: 'Discard' }).click()
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${otherKbId}/add$`))
    await expect(staged.getByText('01_single_claim_complete.json', { exact: true })).toHaveCount(0)

    // Stage a distinctly-named file under kb2, in the same live session.
    await chooseSource(page, 'Documents')
    await page.getByLabel('Document files', { exact: true }).setInputFiles({
      name: '06_zero_entity_resume_like.txt',
      mimeType: 'text/plain',
      buffer: ZERO_ENTITY,
    })
    await expect(staged.getByText('06_zero_entity_resume_like.txt', { exact: true })).toBeVisible()

    // Cross back to kb1 (kb2 is staged now too, so this also prompts).
    await picker.selectOption(kbId)
    await expect(discardDialog).toBeVisible()
    await discardDialog.getByRole('button', { name: 'Discard' }).click()
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/add$`))

    // The leak this regression guards against: kb1's stage must never show
    // kb2's filename. Proven without the store ever being wiped, so this
    // discriminates correct per-KB keying from a reintroduced shared slot.
    await expect(staged.getByText('06_zero_entity_resume_like.txt', { exact: true })).toHaveCount(0)
  })

  test('a submitted run and its receipt survive a page reload', async ({ page }) => {
    await page.goto(`/knowledge-bases/${kbId}/add`)
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

    // A submission that succeeded belongs to the server now: the draft
    // clears and the workspace navigates to Runs to watch its consequence.
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/runs$`), {
      timeout: 60_000,
    })

    const timeline = page.getByRole('list', { name: /ingestion runs/i })
    await expect(timeline.getByText('ingestion', { exact: true }).first()).toBeVisible({
      timeout: 120_000,
    })
    const before = await timeline.getByRole('listitem').count()

    await page.reload()
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/runs$`))
    // Runs used to be a client-side log: a reload erased them.
    await expect(timeline.getByRole('listitem')).toHaveCount(before, { timeout: 60_000 })
  })

  test('the inventory tells the truth about a document that produced no entities', async ({
    page,
  }) => {
    // Confirm the real condition against the API first, then reload for a
    // guaranteed-fresh read: the already-mounted Data page's document query
    // has no polling interval, and the backend reliably reaches
    // `extracted_empty` within a couple of seconds on the real stack
    // regardless of whether an already-open page's query happens to reflect
    // it — see waitForDocument.ts.
    await waitForDocumentStatus(API, kbId, '06_zero_entity_resume_like.txt', ['extracted_empty'])

    await page.goto(`/knowledge-bases/${kbId}/data`)

    const zeroEntityRow = page.getByRole('button', { name: /06_zero_entity_resume_like\.txt/ })
    await expect(zeroEntityRow).toBeVisible()
    // Used to render a green "ready" chip for a document that contributed nothing.
    await expect(zeroEntityRow.getByText('No entities')).toBeVisible()

    await page.getByLabel('Filter documents by status').selectOption('extracted_empty')
    const rows = page.locator('.knowledge-base-document-row')
    await expect(rows).toHaveCount(1, { timeout: 30_000 })
    await expect(rows.first()).toContainText('06_zero_entity_resume_like.txt')

    await page.getByLabel('Filter documents by status').selectOption('all')
    await expect(rows.first()).toBeVisible()
  })

  test('a records submission reports its counts from the server', async ({ page }) => {
    await page.goto(`/knowledge-bases/${kbId}/add`)
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

    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/runs$`), {
      timeout: 60_000,
    })
    const timeline = page.getByRole('list', { name: /ingestion runs/i })
    const counts = timeline.getByText(/\d+ accepted, \d+ duplicate, \d+ rejected/)
    await expect(counts.first()).toBeVisible({ timeout: 120_000 })

    // The counts come from the run, not from this tab: they survive a reload.
    await page.reload()
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}/runs$`))
    await expect(counts.first()).toBeVisible({ timeout: 60_000 })
  })

  test('both deletions require confirmation, and the knowledge base one requires its name', async ({
    page,
  }) => {
    await page.goto(`/knowledge-bases/${kbId}/data`)

    // Removing a document: a plain confirmation that can be cancelled.
    const documentRow = page.getByRole('button', { name: /06_zero_entity_resume_like\.txt/ })
    await expect(documentRow).toBeVisible({ timeout: 60_000 })
    await documentRow.click()
    // Selecting a row updates the ?document= URL param (so a citation can
    // address it), which lands a render cycle after the click — the delete
    // button below reads whichever document is *currently* active, so it has
    // to wait for that render rather than fire in the same tick as the click.
    await expect(documentRow).toHaveClass(/page-list-item--active/)
    await page.getByRole('button', { name: 'Remove document' }).first().dispatchEvent('click')
    const removeDialog = page.getByRole('dialog')
    await expect(removeDialog).toContainText('06_zero_entity_resume_like.txt')
    await removeDialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(documentRow).toBeVisible()

    // Deleting the whole corpus: typed-name confirmation stating the radius.
    await page.goto(`/knowledge-bases/${kbId}/settings`)
    await page.getByRole('button', { name: 'Delete knowledge base' }).dispatchEvent('click')
    const deleteDialog = page.getByRole('dialog')
    await expect(deleteDialog).toContainText('cannot be undone')
    const confirm = deleteDialog.getByRole('button', { name: 'Delete knowledge base' })
    await expect(confirm).toBeDisabled()

    await deleteDialog.getByRole('textbox').fill(kbName)
    await expect(confirm).toBeEnabled()
    await confirm.click()

    // Deleting the knowledge base deletes the address it was read at, so the
    // library is the only place left to be.
    await expect(page).toHaveURL(/\/knowledge-bases$/, { timeout: 60_000 })
    await expect(kbList(page).getByText(kbName, { exact: true })).toHaveCount(0, {
      timeout: 60_000,
    })
    kbDeleted = true
  })
})
