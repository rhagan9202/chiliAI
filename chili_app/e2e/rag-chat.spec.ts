/**
 * RAG Chat (full stack, BL-001). A real conversation is created and a message
 * sent against the seeded KB; the real RAG service returns an assistant reply.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('RAG chat', () => {
  test('sending a message returns a real assistant reply', async ({ page }) => {
    const kb = seeded().knowledge_base_id
    await page.goto(`/rag-chat?kb=${kb}`)

    await expect(page.getByRole('heading', { name: 'RAG Chat' })).toBeVisible()
    await page.getByRole('button', { name: 'New conversation' }).click()

    await page
      .getByPlaceholder('Ask the investigation assistant about an entity, alert, or evidence trail')
      .fill('Why is provider-1 risky?')

    // The Send button enables once the conversation is created (New conversation is async).
    const send = page.getByRole('button', { name: 'Send', exact: true })
    await expect(send).toBeEnabled()
    await send.click()

    await expect(page.locator('.chat-bubble--assistant')).toBeVisible()
  })
})
