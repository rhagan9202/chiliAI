/**
 * Knowledge Bases IA (full stack).
 *
 * The split's whole claim is that the URL owns which knowledge base and which
 * stage you are looking at. These assertions are that claim: a section is
 * addressable, a reload keeps it, the top-bar picker moves between workspaces
 * without changing section, and every pre-split address still lands somewhere
 * correct. No API mocking.
 */
import { expect, test } from '@playwright/test'

import { deleteKnowledgeBase } from './helpers/deleteKb'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

let seededKbId: string
let seededKbName: string
/** A second in-domain knowledge base so the top-bar picker always has
 *  somewhere else to switch to. Relying on another spec's leaked decoy KB
 *  happening to still exist made the picker test pass by accident, not by
 *  design — this spec creates and owns its own switch target instead. */
let secondKbId: string

test.beforeAll(async () => {
  const response = await fetch(`${API}/knowledgebases`)
  if (!response.ok) {
    throw new Error(`GET /knowledgebases failed (${response.status})`)
  }
  const items = ((await response.json()) as {
    items: Array<{ id: string; name: string }>
  }).items
  const seeded = items.find((item) => item.name === 'E2E Seed KB') ?? items[0]
  if (!seeded) {
    throw new Error('no knowledge base available for the workspace navigation spec')
  }
  seededKbId = seeded.id
  seededKbName = seeded.name

  const createRes = await fetch(`${API}/knowledgebases`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name: `kb-nav-e2e-${Date.now()}`, description: 'picker switch target' }),
  })
  if (!createRes.ok) {
    throw new Error(`POST /knowledgebases failed (${createRes.status})`)
  }
  secondKbId = ((await createRes.json()) as { id: string }).id
})

test.afterAll(async () => {
  if (secondKbId) {
    await deleteKnowledgeBase(API, secondKbId)
  }
})

test.describe('Knowledge base workspace navigation', () => {
  test('a library card opens that knowledge base’s workspace', async ({ page }) => {
    await page.goto('/knowledge-bases')
    await expect(page.getByRole('heading', { name: 'Knowledge Bases' })).toBeVisible()

    await page
      .getByRole('region', { name: 'Choose a knowledge base' })
      .getByRole('link', { name: new RegExp(seededKbName) })
      .first()
      .click()

    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${seededKbId}$`))
    await expect(page.getByRole('heading', { level: 1, name: seededKbName })).toBeVisible()
  })

  test('each section is a real address that survives a reload', async ({ page }) => {
    for (const section of ['add', 'data', 'runs', 'settings']) {
      await page.goto(`/knowledge-bases/${seededKbId}/${section}`)
      await expect(page.getByRole('heading', { level: 1, name: seededKbName })).toBeVisible()
      await page.reload()
      await expect(page).toHaveURL(new RegExp(`/${section}$`))
      await expect(page.getByRole('heading', { level: 1, name: seededKbName })).toBeVisible()
    }
  })

  test('a legacy ?kb= address redirects to the workspace', async ({ page }) => {
    await page.goto(`/knowledge-bases?kb=${seededKbId}`)
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${seededKbId}$`))
  })

  test('a legacy ?kb=&document= address redirects into the data section', async ({ page }) => {
    await page.goto(`/knowledge-bases?kb=${seededKbId}&document=doc-does-not-exist`)
    await expect(page).toHaveURL(
      new RegExp(`/knowledge-bases/${seededKbId}/data\\?document=doc-does-not-exist$`),
    )
  })

  test('the legacy /knowledgebases path keeps its knowledge base', async ({ page }) => {
    await page.goto(`/knowledgebases?kb=${seededKbId}`)
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${seededKbId}$`))
  })

  test('the top-bar picker moves between workspaces without leaving the section', async ({
    page,
  }) => {
    await page.goto(`/knowledge-bases/${seededKbId}/runs`)
    const picker = page.getByLabel('Active knowledge base')
    await picker.selectOption(secondKbId)
    await expect(page).toHaveURL(new RegExp(`/knowledge-bases/${secondKbId}/runs$`))
  })

  test('an unknown knowledge base id says so instead of showing another corpus', async ({
    page,
  }) => {
    await page.goto('/knowledge-bases/kb-does-not-exist')
    await expect(page.getByText(/could not be opened/i)).toBeVisible()
  })
})
