/**
 * An entity deep link with no `?kb=` recovers instead of dead-ending (UXA-104).
 *
 * `/investigation/provider-1` resolved against whatever knowledge base the
 * workspace happened to point at and died with "the selected entity could not
 * be loaded" — a frame naming neither the cause nor a next step. Any bookmark,
 * shared link, or refresh that dropped the query landed there.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

/** A real, empty knowledge base for the workspace to be pointing at. */
async function createDecoyKnowledgeBase(): Promise<string> {
  const response = await fetch(`${API}/knowledgebases`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name: `deep-link-decoy-${Date.now()}`, description: 'UXA-104' }),
  })
  expect(response.ok, `KB create failed with ${response.status}`).toBe(true)
  return ((await response.json()) as { id: string }).id
}

test.describe('Entity deep links', () => {
  test('offers a one-click switch to the knowledge base that holds the entity', async ({
    page,
  }) => {
    const { entity_id: entityId } = seeded()
    // The workspace resolver (UXA-101) already recovers a bare deep link when
    // the only ready KB happens to hold the entity, so this points it at a
    // *real* knowledge base that does not — the case that still dead-ended.
    const decoy = await createDecoyKnowledgeBase()

    // Cases uses the shared workspace hook, so `?kb=` there is remembered.
    // (The Alert Feed reads `?kb=` straight off the URL and never writes it to
    // the workspace store — a separate inconsistency, noted on #47.)
    await page.goto(`/cases?kb=${decoy}`)
    await page.goto(`/investigation/${entityId}`)

    const recovery = page.getByText('This entity is in another knowledge base')
    await expect(recovery).toBeVisible()

    const switchLink = page.getByRole('link', { name: /^Switch to / })
    await expect(switchLink).toBeVisible()
    await switchLink.click()

    // Following it actually loads the entity rather than looping.
    await expect(page).toHaveURL(new RegExp(`/investigation/${entityId}\\?kb=`))
    await expect(page.getByTestId('entity-dossier-header')).toBeVisible()
  })

  test('says the entity does not exist rather than that it could not be loaded', async ({
    page,
  }) => {
    await page.goto('/investigation/no-such-entity-anywhere')

    await expect(page.getByText('This entity no longer exists')).toBeVisible()
    await expect(page.getByText(/could not be loaded from the active knowledge base/i)).toHaveCount(
      0,
    )
  })
})
