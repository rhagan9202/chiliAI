/**
 * Layout overflow guard (UXA-201, full stack).
 *
 * The workbench reserves a fixed 248px sidebar and a 340px AI panel, so the
 * content area is ~588px narrower than the viewport. Page breakpoints keyed off
 * the *viewport* therefore fire far too late: at 1440px the Knowledge Bases
 * grid still resolved to `260px 190px 340px`, squeezing the primary work column
 * to 190px and slicing text inside cards that set `overflow-x: hidden`.
 *
 * This spec fails on any element under <main> whose content is wider than its
 * box, across the laptop widths analysts actually use. It asserts the symptom
 * (clipped content) rather than a specific CSS mechanism, so it stays valid if
 * the layout is later reworked.
 */
/// <reference lib="dom" />
// e2e specs compile under tsconfig.node.json (lib: ES2023, no DOM). This is the
// first spec to run DOM code inside page.evaluate, so it pulls the DOM lib in
// file-locally rather than widening the Node config for vite/playwright configs.
import { expect, test, type Page } from '@playwright/test'

import { seeded } from './helpers/seeded'

interface Overflowing {
  cls: string
  tag: string
  clientWidth: number
  scrollWidth: number
  overflowX: string
  text: string
}

/** Widths where the reserved chrome bites hardest, plus a roomy control. */
const VIEWPORTS = [1280, 1366, 1440, 1600, 1920]

type OverflowPage = {
  name: string
  path: (kb: string) => string
  prepare?: (page: Page) => Promise<void>
}

const cockpitPath = () => {
  const { alert_id: alert, case_id: caseId, entity_id: entity, evidence_pack_id: evidence, knowledge_base_id: kb } =
    seeded()
  return `/investigation/${entity}?kb=${kb}&alert=${alert}&case=${caseId}&evidence=${evidence}`
}

const PAGES: OverflowPage[] = [
  { name: 'Knowledge Bases', path: (kb: string) => `/knowledge-bases?kb=${kb}` },
  { name: 'Dashboard', path: () => '/dashboard' },
  { name: 'Alert Feed', path: () => '/alerts' },
  { name: 'Cases', path: () => '/cases' },
  { name: 'Investigation Cockpit Signals', path: cockpitPath },
  {
    name: 'Investigation Cockpit Network',
    path: cockpitPath,
    prepare: async (page) => {
      await page.getByRole('tab', { name: 'Network' }).click()
      await expect(page.getByTestId('investigation-graph-canvas')).toBeVisible()
    },
  },
  {
    name: 'Investigation Cockpit Evidence',
    path: cockpitPath,
    prepare: async (page) => {
      await page.getByRole('button', { name: 'View cockpit evidence' }).click()
      await expect(page.getByTestId('evidence-pack-viewer')).toBeVisible()
    },
  },
]

test.describe('Layout overflow', () => {
  for (const viewportWidth of VIEWPORTS) {
    test(`no content is clipped at ${viewportWidth}px`, async ({ page }) => {
      await page.setViewportSize({ width: viewportWidth, height: 900 })
      const kb = seeded().knowledge_base_id
      const offenders: { page: string; items: Overflowing[] }[] = []

      for (const target of PAGES) {
        await page.goto(target.path(kb))
        await target.prepare?.(page)
        // Let the grid settle before measuring.
        await expect(page.locator('main')).toBeVisible()
        await page.waitForTimeout(600)

        const items = await page.evaluate(() => {
          const found: Overflowing[] = []
          for (const el of Array.from(document.querySelectorAll('main *'))) {
            // SVG elements do not report meaningful client/scroll widths; chart
            // axis rendering is covered by its own spec, not this guard.
            if (!(el instanceof HTMLElement)) continue
            const element = el
            const style = getComputedStyle(element)
            // Elements that scroll their own content are doing so on purpose
            // (the housing table wrapper is the in-repo precedent).
            if (style.overflowX === 'auto' || style.overflowX === 'scroll') continue
            // Native form controls own their own overflow. A <select> reports
            // the intrinsic width of its widest option, which no CSS can wrap
            // or ellipsize: the closed control truncates with an ellipsis and
            // the popup renders every option in full. Without this carve-out
            // any knowledge base whose name is longer than its rail fails the
            // guard, which is a fact about the data, not about the layout.
            // Same for a single-line <input>: its scrollWidth is the width of
            // the value someone typed, which the control scrolls internally as
            // the caret moves. Neither is a layout defect this guard can fix.
            if (element.tagName === 'SELECT' || element.tagName === 'INPUT') continue
            // Screen-reader-only labels are *deliberately* clipped to 1px via
            // the standard `clip: rect(0 0 0 0)` pattern — e.g. the tab panel
            // headings and the "Source type" fieldset legend.
            if (style.position === 'absolute' && style.clip !== 'auto') continue
            // ForceGraph's empty internal canvas wrappers report a persistent
            // 2px scrollWidth delta even when the visible canvas is clipped by
            // the stable graph boundary. Text/UI clipping is what this guard
            // owns; graph rendering is asserted via the canvas test id.
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
        })

        if (items.length > 0) {
          offenders.push({ page: target.name, items })
        }
      }

      expect(
        offenders,
        `Clipped content at ${viewportWidth}px:\n${JSON.stringify(offenders, null, 2)}`,
      ).toEqual([])
    })
  }
})
