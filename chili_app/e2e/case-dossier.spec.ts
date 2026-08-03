/**
 * Case dossier export (full stack, SAFE-CMS-008). The dev seed leaves one alert
 * unpromoted; promoting it should preserve the originating alert/evidence
 * context and make the case-level dossier export cite the source provenance.
 */
import { readFile } from 'node:fs/promises'

import { expect, test } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Case dossier export', () => {
  test.use({ acceptDownloads: true })

  test('promotes an alert and exports cited evidence from the selected case dossier', async ({
    page,
  }) => {
    const kb = seeded().knowledge_base_id

    await page.goto(`/cases?kb=${kb}`)

    const promote = page.getByRole('button', { name: 'Promote Redwood DME Group to case' }).first()
    await expect(promote).toBeVisible()
    await promote.click()

    const dossier = page.getByRole('region', { name: 'Case dossier' })
    await expect(page).toHaveURL(/\/cases\?kb=.*&case=/)
    await expect(dossier).toBeVisible()
    await expect(dossier.getByText('Evidence bundle')).toBeVisible()
    await expect(dossier.getByText('Outlier billing concentration')).toBeVisible()
    await expect(dossier.getByText('Seed source document')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await dossier.getByRole('button', { name: 'Export dossier Markdown' }).click()
    const download = await downloadPromise

    expect(download.suggestedFilename()).toMatch(/^case-.+\.md$/)
    const downloadPath = await download.path()
    expect(downloadPath).toBeTruthy()

    const markdown = await readFile(downloadPath!, 'utf-8')
    expect(markdown).toContain('Outlier billing concentration')
    expect(markdown).toContain('Seed source document')
    expect(markdown).toContain('dev-seed-source')
  })
})
