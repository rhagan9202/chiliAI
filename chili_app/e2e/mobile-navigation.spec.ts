/**
 * Every nav item is reachable at 390px (UXA-105).
 *
 * The sidebar became a horizontally-scrolling strip cut off mid-word —
 * "Dashboard | Alert Feed | Investig…" — with Knowledge Bases and RAG Chat
 * off-screen and no scroll cue, chevron or drawer to say more existed.
 */
import { test, expect } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

interface DomainFeatures {
  enabled_pages: string[]
  roles: Record<string, { pages: string[] }>
  default_role: string
}

test.use({ viewport: { width: 390, height: 844 } })

test.describe('Mobile navigation', () => {
  test('shows every nav item the active pack and role grant', async ({ page }) => {
    const features = (await (await fetch(`${API}/config/features`)).json()) as DomainFeatures
    const rolePages = features.roles[features.default_role]?.pages ?? features.enabled_pages
    const expected = features.enabled_pages.filter((id) => rolePages.includes(id))
    expect(expected.length).toBeGreaterThan(3)

    await page.goto('/alerts')
    const nav = page.getByRole('navigation').first()
    await expect(nav).toBeVisible()

    // Every granted page renders a link, and every link is actually on screen
    // — the previous strip rendered them all but scrolled most out of view.
    const links = nav.getByRole('link')
    await expect(links).toHaveCount(expected.length)
    for (let index = 0; index < expected.length; index += 1) {
      await expect(links.nth(index)).toBeInViewport()
    }
  })

  test('holds no nav content outside its own box', async ({ page }) => {
    await page.goto('/alerts')

    // Measured on the nav container, not the links: a `nowrap` link inside an
    // `overflow-x: auto` strip reports no overflow of its own, so asserting on
    // the link would pass against the very layout this ticket is about.
    const overflow = await page.evaluate(() => {
      const nav = document.querySelector('.app-sidebar__nav') as HTMLElement | null
      return nav === null ? null : { scroll: nav.scrollWidth, client: nav.clientWidth }
    })

    expect(overflow).not.toBeNull()
    expect(overflow!.scroll).toBeLessThanOrEqual(overflow!.client + 1)
  })

  test('the active item is visible without scrolling the nav', async ({ page }) => {
    await page.goto('/knowledge-bases')

    const active = page.locator('.app-sidebar__link--active')
    await expect(active).toBeVisible()
    await expect(active).toBeInViewport()
  })
})
