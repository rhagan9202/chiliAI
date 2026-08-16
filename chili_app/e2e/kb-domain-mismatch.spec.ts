/**
 * KB domain mismatch warning (full stack).
 *
 * Proves the domain-reconfigurability thesis end to end: a knowledge base
 * created under the active domain (the medicare exemplar by default) is
 * stamped with that domain; after the active pack is swapped to a different
 * domain, the KB is scoped out of the studio's default (active-domain) list,
 * and the show-all-domains toggle reveals it with a warn-only badge — nothing
 * is blocked.
 *
 * No page.route mocking — the UI talks to the real API. The domain swap and
 * cleanup use the real admin endpoints (/config/packs, /config/switch,
 * DELETE /knowledgebases/{id}) via Playwright's request fixture.
 *
 * PRECONDITION: the anonymous dev session must be admin-capable
 * (CHILI_DEV_ANONYMOUS_ROLE=admin), because pack listing/switching and KB
 * deletion are admin-gated. The default `make test-e2e` target exports
 * analyst; run this spec with the stack brought up under admin.
 * The spec restores the original active pack and deletes the KB it created,
 * so the shared seeded scenario is left untouched.
 */

import { test, expect } from '@playwright/test'
import type { APIRequestContext } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

type PackSummary = {
  name: string
  path: string
  domain_name: string | null
  valid: boolean
  active: boolean
}

type PackListResponse = {
  packs: PackSummary[]
  active: { config_path: string | null; pack_name: string | null }
}

async function activeDomainName(request: APIRequestContext): Promise<string> {
  const res = await request.get(`${API}/config/domain`)
  expect(res.ok(), 'GET /config/domain must succeed').toBeTruthy()
  const body = (await res.json()) as { domain: { name: string } }
  return body.domain.name
}

async function switchPack(request: APIRequestContext, pack: string): Promise<void> {
  const res = await request.post(`${API}/config/switch`, { data: { pack } })
  expect(res.ok(), `POST /config/switch to '${pack}' must succeed (admin role required)`).toBeTruthy()
}

test.describe('KB domain mismatch warning', () => {
  test('a KB created under the original domain warns after a domain swap', async ({
    page,
    request,
  }) => {
    // --- Discover the current domain and an alternative pack to swap to. ---
    const originalDomain = await activeDomainName(request)

    const packsRes = await request.get(`${API}/config/packs`)
    expect(
      packsRes.ok(),
      'GET /config/packs must succeed — run the stack with CHILI_DEV_ANONYMOUS_ROLE=admin',
    ).toBeTruthy()
    const packList = (await packsRes.json()) as PackListResponse

    const originalPackRef =
      packList.active.config_path ??
      packList.packs.find((pack) => pack.domain_name === originalDomain)?.path
    expect(originalPackRef, 'the active pack must be resolvable for restore').toBeTruthy()

    const alternates = packList.packs.filter(
      (pack) => pack.valid && pack.domain_name !== null && pack.domain_name !== originalDomain,
    )
    // The mismatch badge is only observable when both packs read the SAME KB
    // store, so prefer the food_supply_chain exemplar (pins the identical
    // dev-stack storage) as a deterministic swap target instead of whichever
    // pack happens to sort first. A pack without infra pins would fall back
    // to per-process default stores, making KBs created under the original
    // domain wholly absent after the swap — real platform behavior, but not
    // the warn-badge contract this spec pins.
    const otherPack =
      alternates.find((pack) => pack.domain_name === 'food_supply_chain') ?? alternates[0]
    expect(
      otherPack,
      'at least one valid pack for a different domain must exist (e.g. food_supply_chain)',
    ).toBeTruthy()

    const kbName = `Domain mismatch e2e ${Date.now()}`
    let kbId: string | null = null
    let swapped = false

    try {
      // --- Create a KB through the real UI under the original domain. ---
      await page.goto('/knowledge-bases')
      await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()

      await page.locator('details.kb-library__create summary').click()
      await page.getByLabel(/knowledge base name/i).fill(kbName)
      await page.getByLabel(/^description$/i).fill('Created before a domain swap (e2e).')
      await page.getByRole('button', { name: /create knowledge base/i }).click()

      // Creation lands directly in the new KB's Add data workspace.
      await expect(page).toHaveURL(/\/knowledge-bases\/[^/]+\/add$/)
      kbId = /\/knowledge-bases\/([^/]+)\/add$/.exec(page.url())?.[1] ?? null
      expect(kbId, 'the created KB id must be resolvable from the post-create URL').toBeTruthy()

      // --- Swap the active domain pack (real admin endpoint). ---
      await switchPack(request, otherPack!.path)
      swapped = true
      expect(await activeDomainName(request)).toBe(otherPack!.domain_name)

      // --- The KB now warns in the library, and nothing is blocked. ---
      await page.goto('/knowledge-bases')
      await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()

      const kbCard = page.getByRole('link', { name: new RegExp(kbName) })

      // The library scopes its card list to the active domain by default, so
      // the mismatched KB is hidden until the show-all-domains toggle reveals it.
      await expect(kbCard).toHaveCount(0)
      await page.getByTestId('kb-show-all-domains-toggle').click()

      await expect(kbCard).toBeVisible()
      await expect(kbCard.getByTestId('kb-domain-mismatch')).toBeVisible()
      await expect(kbCard.getByText(`Created under ${originalDomain}`)).toBeVisible()

      // Warn only: the mismatched KB is still openable, and its workspace
      // overview explains the mismatch without disabling anything.
      await kbCard.click()
      await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${kbId}$`))
      const note = page.getByTestId('kb-domain-mismatch-note')
      await expect(note).toBeVisible()
      await expect(note).toContainText(`created under the "${originalDomain}" domain`)

      await page.goto(`/knowledge-bases/${kbId}/settings`)
      await expect(page.getByRole('button', { name: 'Delete knowledge base' })).toBeEnabled()
    } finally {
      // Restore the original pack first so the rest of the suite (and the
      // seeded scenario) keeps running under the expected domain.
      if (swapped && originalPackRef) {
        await switchPack(request, originalPackRef)
      }
      if (kbId) {
        const deleteRes = await request.delete(`${API}/knowledgebases/${kbId}`)
        expect(deleteRes.ok(), 'cleanup DELETE of the e2e KB must succeed').toBeTruthy()
      }
    }
  })
})
