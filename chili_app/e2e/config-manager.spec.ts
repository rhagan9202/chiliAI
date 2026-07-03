/**
 * Config Manager (full stack) — the reconfigurability proof.
 *
 * Switches the active domain pack from the UI and watches the workspace
 * (topbar title, sidebar nav labels) re-render in place without a reload,
 * then exercises the active-pack editor's validate-error rendering against
 * the real POST /config/validate.
 *
 * Requirements:
 * - Full stack running (make dev) — no API mocking anywhere in this spec.
 * - An admin session: the pack-management routes are gated by
 *   require_role("admin"). For the anonymous dev session set
 *   CHILI_DEV_ANONYMOUS_ROLE=admin on the API container. When the session
 *   is not admin the suite skips with a loud message rather than failing.
 * - The stock packs in backend/config/defaults: the spec switches to
 *   food_supply_chain and restores the originally active pack afterwards
 *   (cleanup runs through the real API so later specs keep their seeded
 *   medicare data).
 * - Both stock packs expose the configuration page to the "supervisor"
 *   persona only (the default persona is "analyst"), so the spec selects
 *   supervisor in the topbar before navigating.
 */

import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

const FOOD_PACK = 'food_supply_chain'
const FOOD_DISPLAY_NAME = 'Food Supply Chain Integrity'
/** Nav label unique to the food pack — proves nav re-rendered from config. */
const FOOD_NAV_LABEL = 'Traceability Workbench'

type PackSummary = {
  name: string
  valid: boolean
  active: boolean
}

type PackListResponse = {
  packs: PackSummary[]
  generation: number
}

async function sessionIsAdmin(request: APIRequestContext): Promise<boolean> {
  const res = await request.get(`${API}/auth/me`)
  if (!res.ok()) {
    return false
  }
  const me = (await res.json()) as { roles?: string[] }
  return (me.roles ?? []).includes('admin')
}

async function activePackName(request: APIRequestContext): Promise<string | null> {
  const res = await request.get(`${API}/config/packs`)
  if (!res.ok()) {
    return null
  }
  const body = (await res.json()) as PackListResponse
  return body.packs.find((pack) => pack.active)?.name ?? null
}

/**
 * Reach /configuration: the page id is gated to the supervisor persona in
 * both stock packs, so pick that persona in the topbar first.
 */
async function openConfigurationPage(page: Page): Promise<void> {
  await page.goto('/')
  const roleSelect = page.locator('.app-topbar__select')
  await expect(roleSelect).toBeVisible()
  await roleSelect.selectOption('supervisor')
  await page
    .locator('aside[aria-label="Primary navigation"]')
    .getByText('Configuration')
    .click()
  await expect(page.getByRole('heading', { name: 'Configuration' })).toBeVisible()
}

async function switchViaUi(page: Page, packName: string): Promise<void> {
  const item = page.getByTestId(`pack-item-${packName}`)
  await expect(item).toBeVisible()
  await item.getByRole('button', { name: 'Activate' }).click()
  await item.getByRole('button', { name: 'Confirm switch' }).click()
  await expect(page.getByTestId('swap-result')).toBeVisible()
}

test.describe('Config Manager', () => {
  let originalPack: string | null = null

  test.beforeEach(async ({ request }) => {
    test.skip(
      !(await sessionIsAdmin(request)),
      'Config Manager e2e needs an admin session — set CHILI_DEV_ANONYMOUS_ROLE=admin on the API and restart the stack.',
    )
  })

  test.afterEach(async ({ request }) => {
    // Restore the originally active pack through the real API so later specs
    // (which depend on the seeded medicare scenario) are unaffected even if
    // an assertion above failed mid-switch.
    if (originalPack !== null && (await activePackName(request)) !== originalPack) {
      const res = await request.post(`${API}/config/switch`, {
        data: { pack: originalPack },
      })
      expect(res.ok(), `restoring pack '${originalPack}' failed: ${res.status()}`).toBe(true)
    }
    originalPack = null
  })

  test('switching domains hot-swaps nav and labels in place', async ({ page, request }) => {
    originalPack = await activePackName(request)
    expect(originalPack, 'an active pack must be resolvable before switching').not.toBeNull()
    test.skip(
      originalPack === FOOD_PACK,
      'The food pack is already active; the swap round-trip needs a different starting pack.',
    )

    await openConfigurationPage(page)

    // Admin affordances render; capture the pre-swap workspace chrome.
    const switcher = page.getByTestId('pack-switcher')
    await expect(switcher).toBeVisible()
    await expect(page.getByTestId(`pack-item-${originalPack}`)).toHaveClass(
      /pack-switcher__item--active/,
    )
    const title = page.locator('.app-topbar__title')
    const originalTitle = await title.textContent()
    const sidebar = page.locator('aside[aria-label="Primary navigation"]')
    await expect(sidebar.getByText(FOOD_NAV_LABEL)).toHaveCount(0)

    // Switch to the food pack from the UI (Activate -> confirm step).
    await switchViaUi(page, FOOD_PACK)
    await expect(page.getByTestId('swap-result')).toContainText(FOOD_PACK)

    // Hot swap: no reload — topbar title and sidebar nav re-render from the
    // refetched domain config in place.
    await expect(title).toHaveText(FOOD_DISPLAY_NAME)
    await expect(sidebar.getByText(FOOD_NAV_LABEL)).toBeVisible()

    // The pack list refetches and now marks the food pack active.
    await expect(page.getByTestId(`pack-item-${FOOD_PACK}`)).toHaveClass(
      /pack-switcher__item--active/,
    )

    // Switch back from the UI and watch the workspace revert in place.
    await switchViaUi(page, originalPack as string)
    await expect(title).toHaveText(originalTitle ?? '')
    await expect(sidebar.getByText(FOOD_NAV_LABEL)).toHaveCount(0)
  })

  test('editor renders field-level validation errors from the real validator', async ({
    page,
    request,
  }) => {
    originalPack = await activePackName(request)

    await openConfigurationPage(page)
    const editor = page.getByTestId('active-pack-editor')
    await expect(editor).toBeVisible()

    // The buffer seeds from the active domain config; Apply is gated until a
    // successful validate of the current buffer.
    await expect(editor.getByRole('button', { name: 'Apply' })).toBeDisabled()

    // Replace the buffer with a structurally valid YAML mapping that fails
    // full DomainConfig validation (missing display_name, entities, ...).
    const content = editor.locator('[data-testid="yaml-editor"] .cm-content')
    await content.click()
    await page.keyboard.press('ControlOrMeta+a')
    await page.keyboard.type('domain:\n  name: e2e_broken_pack')
    await editor.getByRole('button', { name: 'Validate' }).click()

    // Real POST /config/validate returns structured field-level issues which
    // render inline; Apply stays gated.
    const issues = page.getByTestId('validation-issues')
    await expect(issues).toBeVisible()
    await expect(issues.locator('.config-manager__issue-field').first()).toBeVisible()
    await expect(editor.getByRole('button', { name: 'Apply' })).toBeDisabled()

    // Reset restores the active-config buffer and clears the issues.
    await editor.getByRole('button', { name: 'Reset to active config' }).click()
    await expect(issues).toHaveCount(0)
  })
})
