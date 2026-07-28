/**
 * Promotion reaches what it created (UXA-405).
 *
 * Promoting an alert succeeded with a well-worded toast that carried no link,
 * so the case the analyst had just made was unreachable from the feed. The
 * alert also still read OPEN and its button looked clickable again.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

test.describe('Promote to case', () => {
  test('the toast opens the case it created, and the alert reflects it', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/alerts?kb=${kb}`)

    const promote = page.getByRole('button', { name: /^Promote .+ to case$/ }).first()
    // A previous spec in the same serial run may already have promoted it.
    test.skip(!(await promote.isVisible()), 'seeded alert already promoted')
    await promote.click()

    const toast = page.getByRole('status').filter({ hasText: /Promoted .+ to a case/ })
    await expect(toast).toBeVisible()

    // The alert now says it is promoted and refuses a second one.
    await expect(page.getByRole('button', { name: /^Promoted .+ to case$/ })).toBeDisabled()

    await toast.getByRole('link', { name: 'Open case' }).click()
    await expect(page).toHaveURL(/\/cases\?/)
    await expect(page).toHaveURL(/case=/)
    await expect(page.getByRole('heading', { level: 1, name: 'Case Management' })).toBeVisible()
  })

  test('the evidence pack is dated and says what it drew on', async ({ page }) => {
    const { knowledge_base_id: kb, alert_id: alertId } = seeded()
    // `?alert=` opens the panel directly; the toggle then reads "Hide evidence".
    await page.goto(`/alerts?kb=${kb}&alert=${alertId}`)

    const pack = page.getByTestId('evidence-pack-viewer')
    await expect(pack).toBeVisible()
    await expect(pack.getByText(/^Generated /)).toBeVisible()
    await expect(pack.getByText(/Evidence confidence \d+%/)).toBeVisible()
  })

  test('the evidence pack exports as Markdown (UXA-405)', async ({ page }) => {
    const { knowledge_base_id: kb, alert_id: alertId, evidence_pack_id: packId } = seeded()
    await page.goto(`/alerts?kb=${kb}&alert=${alertId}`)

    const actions = page.getByTestId('evidence-pack-actions')
    await expect(actions).toBeVisible()

    // A real download, rendered by the real API — the pack could not leave the
    // browser at all before this.
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      actions.getByRole('button', { name: 'Export Markdown' }).click(),
    ])

    expect(download.suggestedFilename()).toBe(`evidence-${packId}.md`)
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream) chunks.push(Buffer.from(chunk))
    const content = Buffer.concat(chunks).toString('utf-8')
    expect(content).toContain(`- **Evidence pack:** \`${packId}\``)
    expect(content).toContain('## Reasoning')
  })

  test('an alert attaches to a case that already exists (UXA-405)', async ({ page, request }) => {
    const { knowledge_base_id: kb, alert_id: alertId } = seeded()
    const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

    // A case the seeded alert is not already in, so the picker has something to
    // offer. Created through the real API, like the rest of this spec's state.
    const created = await request.post(`${API}/cases?knowledge_base_id=${kb}`, {
      data: { title: `Attach target ${Date.now()}`, priority: 'medium' },
    })
    expect(created.ok()).toBeTruthy()
    const targetCase = (await created.json()).case as { id: string; title: string }

    await page.goto(`/alerts?kb=${kb}&alert=${alertId}`)
    await page.getByTestId('evidence-pack-actions').getByRole('button', { name: 'Attach to case' }).click()

    const [response] = await Promise.all([
      page.waitForResponse(
        (r) => /\/cases\/.+\/alerts/.test(r.url()) && r.request().method() === 'POST',
      ),
      page
        .getByTestId('evidence-attach-picker')
        .getByLabel('Attach to')
        .selectOption({ label: targetCase.title }),
    ])
    expect(response.ok()).toBeTruthy()

    // The toast reaches the case it just grew.
    const toast = page.getByRole('status').filter({ hasText: /Attached to / })
    await expect(toast).toBeVisible()
    await toast.getByRole('link', { name: 'Open case' }).click()
    await expect(page).toHaveURL(new RegExp(`case=${targetCase.id}`))

    // Durable: the case now holds the alert, per the real API.
    const detail = await request.get(`${API}/cases/${targetCase.id}?knowledge_base_id=${kb}`)
    const body = await detail.json()
    expect(body.case.alert_ids).toContain(alertId)
    expect(body.entity_timeline.at(-1).label).toBe('Alert attached')
  })
})
