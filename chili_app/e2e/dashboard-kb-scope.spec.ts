/**
 * The Dashboard reports on ONE knowledge base (UXA-408).
 *
 * `GET /analytics/overview` took no parameters and summed every knowledge
 * base, so the KPI tiles disagreed with the rest of the page the moment a
 * second KB held data. This drives the real endpoint with two seeded KBs and
 * asserts the tiles follow the selection.
 */
import { test, expect } from '@playwright/test'

import { seeded } from './helpers/seeded'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

interface Overview {
  active_alerts: number
  open_cases: number
  entities_monitored: number
  high_risk_entities: number
}

async function overview(kb?: string): Promise<Overview> {
  const url = kb ? `${API}/analytics/overview?kb=${encodeURIComponent(kb)}` : `${API}/analytics/overview`
  const response = await fetch(url)
  expect(response.ok, `GET ${url} failed with ${response.status}`).toBe(true)
  return (await response.json()) as Overview
}

/**
 * A second knowledge base holding its own case. Without it every assertion
 * here would pass unscoped too — one KB holding all the data is exactly why
 * the defect went unnoticed.
 */
async function createDecoyKnowledgeBase(): Promise<string> {
  const created = await fetch(`${API}/knowledgebases`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ name: `scope-decoy-${Date.now()}`, description: 'UXA-408 scope decoy' }),
  })
  expect(created.ok, `KB create failed with ${created.status}`).toBe(true)
  const kb = (await created.json()) as { id: string }

  const caseResponse = await fetch(
    `${API}/cases?knowledge_base_id=${encodeURIComponent(kb.id)}`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ title: 'Decoy case', priority: 'low', alert_ids: [] }),
    },
  )
  expect(caseResponse.ok, `case create failed with ${caseResponse.status}`).toBe(true)
  return kb.id
}

test.describe('Dashboard knowledge base scope', () => {
  test('the scoped overview counts one knowledge base, the unscoped one counts all', async () => {
    const { knowledge_base_id: kb } = seeded()
    const decoy = await createDecoyKnowledgeBase()

    const seededScope = await overview(kb)
    const decoyScope = await overview(decoy)
    const workspace = await overview()
    const ghost = await overview('kb-does-not-exist')

    expect(seededScope.active_alerts).toBeGreaterThan(0)

    // The decoy's case must NOT appear in the seeded KB's figures, and must
    // appear in the workspace-wide ones.
    expect(decoyScope.open_cases).toBe(1)
    expect(workspace.open_cases).toBeGreaterThan(seededScope.open_cases)
    expect(decoyScope.active_alerts).toBe(0)

    // An unknown id reads as empty rather than silently answering
    // workspace-wide, which would be a different question.
    expect(ghost).toMatchObject({
      active_alerts: 0,
      open_cases: 0,
      entities_monitored: 0,
      high_risk_entities: 0,
    })
  })

  test("the Open cases tile agrees with the Cases page for the same knowledge base", async ({
    page,
  }) => {
    const { knowledge_base_id: kb } = seeded()
    // A second KB with its own case, so an unscoped tile would over-count.
    await createDecoyKnowledgeBase()

    await page.goto(`/dashboard?kb=${kb}`)
    const tile = page.getByRole('link', { name: /Open cases/i }).first()
    await expect(tile).toBeVisible()
    const onDashboard = (await tile.innerText()).match(/\d+/)?.[0]

    await page.goto(`/cases?kb=${kb}`)
    const chip = page.locator('.section-header__actions .ui-chip').first()
    await expect(chip).toBeVisible()
    const onCases = (await chip.innerText()).match(/\d+/)?.[0]

    expect(onDashboard).toBe(onCases)
  })

  test('the header names the knowledge base the figures cover', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()

    await page.goto(`/dashboard?kb=${kb}`)

    await expect(page.getByTestId('dashboard-scope')).toHaveText('E2E Seed KB')
  })
})
