/**
 * Investigation Workbench (full stack, BL-003 + U2 reshape). Navigating to the
 * seeded entity loads the dossier (header + capability-gated tabs); the graph
 * canvas mounts under the Network tab.
 */
import { test, expect, type Locator, type Page } from '@playwright/test'

import { seeded } from './helpers/seeded'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

const COCKPIT_VIEWPORTS = [
  { name: 'desktop', width: 1366, height: 900 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'mobile', width: 390, height: 844 },
]

interface Overflowing {
  cls: string
  tag: string
  clientWidth: number
  scrollWidth: number
  overflowX: string
  text: string
}

async function expectInsideViewport(locator: Locator, viewport: { width: number; height: number }) {
  await expect(locator).toBeVisible()
  const box = await locator.boundingBox()
  expect(box).not.toBeNull()
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.y).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width)
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height)
}

async function expectRegionHasNoHorizontalOverflow(page: Page, selector: string) {
  await expect(page.locator(selector)).toBeVisible()
  const items = await page.evaluate((rootSelector) => {
    const root = document.querySelector(rootSelector)
    if (!root) return [{ cls: rootSelector, tag: 'MISSING', clientWidth: 0, scrollWidth: 0, overflowX: '', text: '' }]
    const found: Overflowing[] = []
    for (const el of Array.from(root.querySelectorAll('*'))) {
      if (!(el instanceof HTMLElement)) continue
      const element = el
      const style = getComputedStyle(element)
      if (style.overflowX === 'auto' || style.overflowX === 'scroll') continue
      if (style.position === 'absolute' && style.clip !== 'auto') continue
      if (
        (element.closest('[data-testid="investigation-graph-canvas"]') ||
          element.closest('[data-testid="evidence-pack-subgraph"]')) &&
        (element.textContent ?? '').trim().length === 0
      ) {
        continue
      }
      if (element.clientWidth <= 0) continue
      if (element.scrollWidth > element.clientWidth + 1) {
        found.push({
          cls: String(element.className).slice(0, 70),
          tag: element.tagName,
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
          overflowX: style.overflowX,
          text: (element.textContent ?? '').trim().slice(0, 60),
        })
      }
    }
    return found
  }, selector)

  expect(items, `Clipped cockpit content:\n${JSON.stringify(items, null, 2)}`).toEqual([])
}

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

    // `state: { display: "State" }` in the active pack. `name` and `specialty`
    // are deliberately absent from the property list because they render as
    // the configured title/subtitle in the header.
    await expect(dossier.getByText('State', { exact: true })).toBeVisible()
    await expect(dossier.getByText('Redwood DME Group', { exact: true })).toBeVisible()
    await expect(dossier.getByText('Provider · specialty-1', { exact: true })).toBeVisible()

    // Everything past the leading fields waits behind one control, rather than
    // being silently truncated to four alphabetical keys.
    await page.getByRole('button', { name: /^Show all \d+ properties$/ }).click()
    await expect(dossier.getByText('NPI', { exact: true })).toBeVisible()

    // No raw key survives anywhere in the dossier, and `date` properties are
    // formatted rather than echoed as ISO strings.
    const dossierText = await dossier.innerText()
    expect(dossierText).not.toMatch(/\b[a-z]+_[a-z_]+\b(?=\s*$)/m)
    expect(dossierText).not.toMatch(/\d{4}-\d{2}-\d{2}/)
  })

  for (const viewport of COCKPIT_VIEWPORTS) {
    test(`keeps cockpit controls reachable at ${viewport.name} size`, async ({ page, request }) => {
      const { alert_id: alert, entity_id: entity, evidence_pack_id: evidence, knowledge_base_id: kb } = seeded()
      const created = await request.post(`${API}/cases?knowledge_base_id=${kb}`, {
        data: { title: `Cockpit viewport ${viewport.name}`, priority: 'high', alert_ids: [alert] },
      })
      expect(created.ok()).toBeTruthy()
      const { case: createdCase } = (await created.json()) as { case: { id: string } }

      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(`/investigation/${entity}?kb=${kb}&alert=${alert}&case=${createdCase.id}&evidence=${evidence}`)

      await expect(page.getByRole('group', { name: 'Cockpit overview' })).toBeVisible()
      await expectInsideViewport(page.getByRole('group', { name: 'Cockpit actions' }), viewport)
      await expectInsideViewport(page.getByRole('link', { name: 'Open alert' }), viewport)
      await expectInsideViewport(page.getByRole('link', { name: 'Open case' }), viewport)
      await expectInsideViewport(page.getByRole('button', { name: 'View cockpit evidence' }), viewport)
    })

    test(`keeps cockpit graph and evidence spaces unclipped at ${viewport.name} size`, async ({
      page,
      request,
    }) => {
      const { alert_id: alert, entity_id: entity, evidence_pack_id: evidence, knowledge_base_id: kb } = seeded()
      const created = await request.post(`${API}/cases?knowledge_base_id=${kb}`, {
        data: { title: `Cockpit space ${viewport.name}`, priority: 'high', alert_ids: [alert] },
      })
      expect(created.ok()).toBeTruthy()
      const { case: createdCase } = (await created.json()) as { case: { id: string } }

      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await page.goto(`/investigation/${entity}?kb=${kb}&alert=${alert}&case=${createdCase.id}&evidence=${evidence}`)

      await page.getByRole('tab', { name: 'Network' }).click()
      await expect(page.getByTestId('investigation-graph-canvas')).toBeVisible()
      await expectRegionHasNoHorizontalOverflow(page, '#workbench-tabpanel-network')

      await page.getByRole('button', { name: 'View cockpit evidence' }).click()
      await expect(page.getByTestId('evidence-pack-viewer')).toBeVisible()
      await expectRegionHasNoHorizontalOverflow(page, '#workbench-tabpanel-evidence')
    })
  }
})
