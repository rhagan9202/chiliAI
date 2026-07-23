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
})
