/**
 * Investigation Workbench (full stack, BL-003 + U2 reshape). Navigating to the
 * seeded entity loads the dossier (header + capability-gated tabs); the graph
 * canvas mounts under the Network tab.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Investigation workbench', () => {
  test('renders the dossier tabs and mounts the graph canvas under Network', async ({ page }) => {
    const { knowledge_base_id: kb, entity_id: entity } = seeded()
    await page.goto(`/investigation/${entity}?kb=${kb}`)

    // Once the seeded entity loads, the section heading shows the entity's
    // title (not the literal "Investigation Workbench"), so assert the stable
    // eyebrow plus the U2 dossier structure.
    await expect(page.getByText('Entity workbench')).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Signals' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Network' })).toBeVisible()

    // The canvas is the Network tab's subject (BL-003); it mounts once the
    // tab is selected.
    await page.getByRole('tab', { name: 'Network' }).click()
    await expect(page.getByTestId('investigation-graph-canvas')).toBeVisible()
  })

  test('labels dossier properties from the live domain configuration (UXA-302)', async ({ page }) => {
    const { knowledge_base_id: kb, entity_id: entity } = seeded()
    await page.goto(`/investigation/${entity}?kb=${kb}`)

    const dossier = page.getByTestId('entity-dossier-header')
    await expect(dossier).toBeVisible()

    // `organization_name: { display: "Organization Name" }` in the active pack.
    await expect(dossier.getByText('Organization Name', { exact: true })).toBeVisible()

    // Everything past the leading fields waits behind one control, rather than
    // being silently truncated to four alphabetical keys.
    await page.getByRole('button', { name: /^Show all \d+ properties$/ }).click()
    await expect(dossier.getByText('Primary Taxonomy', { exact: true })).toBeVisible()

    // No raw key survives anywhere in the dossier, and `date` properties are
    // formatted rather than echoed as ISO strings.
    const dossierText = await dossier.innerText()
    expect(dossierText).not.toMatch(/\b[a-z]+_[a-z_]+\b(?=\s*$)/m)
    expect(dossierText).not.toMatch(/\d{4}-\d{2}-\d{2}/)
  })
})
