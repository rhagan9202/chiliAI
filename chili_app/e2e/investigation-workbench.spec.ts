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

    await expect(page.getByRole('heading', { name: 'Investigation Workbench' })).toBeVisible()
    await expect(page.getByTestId('investigation-graph-canvas')).toBeVisible()
  })
})
