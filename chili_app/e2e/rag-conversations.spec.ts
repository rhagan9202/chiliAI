/**
 * Durable conversations are reachable (UXA-403).
 *
 * The backend persisted conversations per knowledge base and the dev seed
 * created one, but the repository had no `list` and the UI had no way to
 * resume anything — a "New conversation" button and nothing else.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('RAG conversations', () => {
  test('lists the seeded conversation and resumes its history', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/rag-chat?kb=${kb}`)

    const list = page.getByRole('list', { name: 'Conversations' })
    await expect(list).toBeVisible()
    const first = list.getByRole('button').first()
    const title = (await first.locator('strong').innerText()).trim()

    await first.click()

    // Resuming must bring the stored exchange back, not just the title.
    await expect(page.locator('.chat-thread')).toBeVisible()
    await expect(page.locator('.chat-bubble').first()).toBeVisible()
    await expect(page.locator('.chat-page__toolbar-controls')).toContainText(title)
  })

  test('starter prompts follow the domain pack and land in the composer', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/rag-chat?kb=${kb}`)

    const starters = page.getByLabel('Starter prompts')
    await expect(starters).toBeVisible()
    // The medicare pack's first entity type, not a hardcoded fraud phrase.
    const prompt = starters.getByRole('button').first()
    const text = (await prompt.innerText()).trim()
    expect(text).toContain('Provider')

    await prompt.click()

    await expect(page.getByPlaceholder(/Ask the investigation assistant/)).toHaveValue(text)
  })

  test('the conversation list is scoped to the active knowledge base', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()

    await page.goto(`/rag-chat?kb=${kb}`)
    await expect(page.getByRole('list', { name: 'Conversations' })).toBeVisible()

    // A knowledge base with no conversations shows none rather than the
    // previous KB's.
    await page.goto('/rag-chat?kb=kb-does-not-exist')
    await expect(page.getByRole('list', { name: 'Conversations' })).toHaveCount(0)
  })
})
