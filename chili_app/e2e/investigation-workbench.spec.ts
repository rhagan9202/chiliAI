/**
 * Investigation Workbench (full stack, BL-003). Navigating to the seeded entity
 * loads its real Neo4j neighborhood and mounts the GraphCanvas.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Investigation workbench', () => {
  test('mounts the graph canvas for the seeded entity neighborhood', async ({ page }) => {
    const { knowledge_base_id: kb, entity_id: entity } = seeded()
    await page.goto(`/investigation/${entity}?kb=${kb}`)

    // Once the seeded entity loads, the section heading shows the entity's
    // title (not the literal "Investigation Workbench"), so assert the stable
    // eyebrow plus the graph canvas — the actual subject of this test (BL-003).
    await expect(page.getByText('Entity workbench')).toBeVisible()
    await expect(page.getByTestId('investigation-graph-canvas')).toBeVisible()
  })
})
