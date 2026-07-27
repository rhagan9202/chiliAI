/**
 * One assistant, two surfaces (UXA-407).
 *
 * The app presented four AI entry points with nothing distinguishing them, and
 * showed two composers side by side on RAG Chat. The rail is the quick ask; it
 * hands its context to RAG Chat, which is the durable conversation.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Assistant model', () => {
  test('the rail says what it is and yields to RAG Chat on its own page', async ({ page }) => {
    const { knowledge_base_id: kb, alert_id: alertId } = seeded()

    await page.goto(`/alerts?kb=${kb}&alert=${alertId}`)
    const rail = page.getByLabel('AI investigator assistant')
    await expect(rail).toContainText('Quick ask — opens in RAG Chat')

    await page.goto(`/rag-chat?kb=${kb}`)
    // Two composers for the same job, with nothing explaining the difference.
    await expect(page.getByLabel('AI investigator assistant')).toHaveCount(0)
    await expect(page.getByPlaceholder(/Ask the investigation assistant/)).toBeVisible()
  })

  test('the rail hands its context to RAG Chat rather than answering alone', async ({ page }) => {
    const { knowledge_base_id: kb, alert_id: alertId } = seeded()
    await page.goto(`/alerts?kb=${kb}&alert=${alertId}`)

    await page.getByLabel('Ask the AI investigator').fill('Why is this flagged?')
    await page.getByRole('button', { name: 'Send message' }).click()

    await expect(page).toHaveURL(/\/rag-chat\?/)
    await expect(page).toHaveURL(new RegExp(`alert=${alertId}`))
    await expect(page).toHaveURL(/q=Why\+is\+this\+flagged/)
  })

  test('Ask AI states where the answer will land before it navigates', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    await expect(page.getByRole('button', { name: /^Ask AI for / }).first()).toHaveAttribute(
      'title',
      /Opens RAG Chat with this alert/,
    )
  })
})
