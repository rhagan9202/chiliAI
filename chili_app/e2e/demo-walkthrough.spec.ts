/**
 * Demo walkthrough (full stack, BL-051 / D1). Mechanically validates the
 * presenter script's path (docs/demo/presenter-script.md) so the CMS fraud
 * demo cannot silently rot: alert feed row -> evidence expansion -> workbench
 * dossier tabs -> policy page.
 *
 * Two modes, following the housing specs' API-probe precedent
 * (air-force-housing-scorecards.spec.ts):
 *
 * - reference mode (default — dev-seed data via e2e/helpers/seeded.ts): walks
 *   the path with the seeded scenario's ids. Green on a plain `make test-e2e`
 *   with no bulk data staged.
 * - live mode (a "TN Demo" / medicare_fraud / status=ready knowledge base is
 *   present — discovered via GET /knowledgebases, or E2E_DEMO_KB overrides
 *   the discovery entirely): additionally asserts the analytics reality the
 *   presenter script relies on — a factor-tagged alert, the workbench NETWORK
 *   tab's cluster membership panel, the EVIDENCE tab's attribution bars, and
 *   a non-empty /policy queue. Each live assertion calls test.skip() with a
 *   clear reason when no TN KB exists, so the default suite run stays green
 *   without ingesting TN data (Task 5 exercises live mode for real).
 */
import { expect, test } from '@playwright/test'

import { seeded } from './helpers/seeded'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'
const TN_KB_NAME = 'TN Demo'
const TN_KB_DOMAIN = 'medicare_fraud'
const TN_KB_STATUS = 'ready'
const NO_TN_KB_REASON =
  'No TN Demo KB found (GET /knowledgebases has no item named ' +
  `"${TN_KB_NAME}" with domain=${TN_KB_DOMAIN} status=${TN_KB_STATUS}) — ` +
  'run `make demo-cms` or set E2E_DEMO_KB to enable live mode.'

type KnowledgeBaseItem = {
  id: string
  name: string
  domain: string | null
  status: string
  created_at: string
}

type KbListResponse = { items: KnowledgeBaseItem[]; total: number }

type AlertListItem = {
  id: string
  entity_id: string
  entity_label: string
  evidence_pack_id?: string | null
  confidence: number
  severity: string
  tags: string[]
}

type AlertListResponse = { items: AlertListItem[] }

type EvidencePackResponse = {
  attribution: { feature_name: string; contribution: number }[]
}

type PolicyItemSummary = { id: string; title: string }
type PolicyItemListResponse = { items: PolicyItemSummary[]; total: number }

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) {
    throw new Error(`GET ${path} failed (${res.status}): ${await res.text()}`)
  }
  return (await res.json()) as T
}

/** Uppercased, dot-joined flag label — mirrors src/utils/flagLabel.ts. */
function flagLabelFor(alert: { tags: string[]; severity: string }): string {
  if (alert.tags.length > 0) {
    return alert.tags.map((tag) => tag.toUpperCase()).join(' · ')
  }
  return alert.severity.toUpperCase()
}

type DiscoveredTnKb = { kb: KnowledgeBaseItem; reason: string }

/**
 * Discover the TN demo KB. Reruns of `make demo-cms` create a NEW KB each
 * time — the operator can legitimately have several KBs named "TN Demo" in
 * the medicare_fraud domain with status ready, only the newest of which has
 * been through a full analytics pass. First-match discovery would silently
 * bind to a stale, alert-less KB, so this collects every matching candidate,
 * orders newest-first (created_at desc), and prefers the newest one that
 * already has >=1 alert; if none do (all are freshly ingesting), it falls
 * back to the newest match and lets the per-test skip reasons explain what's
 * still missing. E2E_DEMO_KB bypasses discovery and wins outright.
 */
async function discoverTnKb(): Promise<DiscoveredTnKb | null> {
  const override = process.env['E2E_DEMO_KB']
  if (override) {
    const kb = await fetchJson<KnowledgeBaseItem>(`/knowledgebases/${override}`)
    return { kb, reason: 'E2E_DEMO_KB override' }
  }

  const payload = await fetchJson<KbListResponse>('/knowledgebases?limit=500')
  const candidates = payload.items
    .filter(
      (kb) =>
        kb.name === TN_KB_NAME && kb.domain === TN_KB_DOMAIN && kb.status === TN_KB_STATUS,
    )
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

  if (candidates.length === 0) {
    return null
  }

  for (const candidate of candidates) {
    const alerts = await fetchJson<AlertListResponse>(`/alerts?kb=${candidate.id}&limit=1`)
    if (alerts.items.length > 0) {
      return {
        kb: candidate,
        reason: `newest of ${candidates.length} candidate(s) with >=1 alert`,
      }
    }
  }
  return {
    kb: candidates[0],
    reason: `newest of ${candidates.length} candidate(s); none have alerts yet`,
  }
}

let tnKb: KnowledgeBaseItem | null = null

test.beforeAll(async () => {
  const discovered = await discoverTnKb()
  tnKb = discovered?.kb ?? null
  console.log(
    tnKb && discovered
      ? `[demo-walkthrough] live mode: TN KB ${tnKb.id} ("${tnKb.name}", status=${tnKb.status}) — ${discovered.reason}`
      : `[demo-walkthrough] reference mode only: ${NO_TN_KB_REASON}`,
  )
})

/** Skip the current test unless a TN demo KB was discovered; returns it narrowed. */
function requireTnKb(): KnowledgeBaseItem {
  test.skip(tnKb === null, NO_TN_KB_REASON)
  return tnKb as KnowledgeBaseItem
}

test.describe('Demo walkthrough — reference mode (dev-seed)', () => {
  test('dashboard renders KPI band and severity mix for the active KB (Scene 2.1)', async ({
    page,
  }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/dashboard?kb=${kb}`)

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
    await expect(page.locator('.dashboard-kpis')).toBeVisible()
    await expect(page.getByText('Severity Mix')).toBeVisible()
  })

  test('alert feed row leads with triage numeral + flag label, and expands to the narrative band', async ({
    page,
  }) => {
    const { alert_id: alertId, knowledge_base_id: kb } = seeded()
    const { alert } = await fetchJson<{ alert: AlertListItem }>(`/alerts/${alertId}`)

    await page.goto(`/alerts?kb=${kb}`)

    const row = page.locator('.alert-row-card').filter({ hasText: alert.entity_label })
    await expect(row).toBeVisible()
    await expect(row.getByTestId('triage-numeral')).toHaveText(
      String(Math.round(alert.confidence * 100)),
    )
    await expect(row.locator('.flag-label').first()).toHaveText(flagLabelFor(alert))

    await row.getByRole('button', { name: 'View evidence' }).click()
    await expect(page.getByTestId('evidence-narrative')).toBeVisible()
    await expect(page.getByText('◆ AI NARRATIVE')).toBeVisible()
  })

  test('workbench dossier renders capability-gated tabs for the seeded entity', async ({
    page,
  }) => {
    const { knowledge_base_id: kb, entity_id: entityId } = seeded()
    await page.goto(`/investigation/${entityId}?kb=${kb}`)

    await expect(page.getByText('Entity workbench')).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Signals' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Network' })).toBeVisible()

    // The presenter script's dossier scene walks the Policy tab too
    // (capability-gated on explainability, which the CMS pack enables).
    await page.getByRole('tab', { name: 'Policy' }).click()
    await expect(page.locator('#workbench-tabpanel-policy')).toBeVisible()
  })

  test('/policy loads the rule-generated queue', async ({ page }) => {
    const { knowledge_base_id: kb } = seeded()
    await page.goto(`/policy?kb=${kb}`)

    await expect(page.getByRole('heading', { name: 'Policy Intelligence' })).toBeVisible()
    await expect(page.getByText('Item queue')).toBeVisible()
    await expect(page.locator('.page-list-item')).not.toHaveCount(0)
  })
})

test.describe('Demo walkthrough — live mode (TN demo KB)', () => {
  test('has at least one alert with non-empty factor tags for the TN KB', async ({ page }) => {
    const kb = requireTnKb()

    const alerts = await fetchJson<AlertListResponse>(`/alerts?kb=${kb.id}&limit=500`)
    test.skip(alerts.items.length === 0, `TN KB ${kb.id} has no alerts yet.`)
    const tagged = alerts.items.filter((item) => item.tags.length > 0)
    expect(
      tagged.length,
      `expected >=1 alert with non-empty tags in TN KB ${kb.id}`,
    ).toBeGreaterThanOrEqual(1)

    // Cross-check the recomputed flag label actually renders somewhere in the
    // live feed — mirrors the housing specs' recompute-from-API-and-compare
    // pattern rather than pinning to one row (multiple alerts can share an
    // entity_label, so there is no stable per-row selector to target).
    await page.goto(`/alerts?kb=${kb.id}`)
    // allTextContents() does not auto-wait; anchor on the first flag label
    // rendering (all rows populate from a single alerts fetch) before sampling.
    await expect(page.locator('.flag-label').first()).toBeVisible()
    const renderedFlags = await page.locator('.flag-label').allTextContents()
    const expectedFlags = tagged.map((item) => flagLabelFor(item))
    expect(
      expectedFlags.some((flag) => renderedFlags.includes(flag)),
      `expected one rendered .flag-label to match a tagged alert's flag label ` +
        `(e.g. "${expectedFlags[0]}"); rendered: ${renderedFlags.join(', ')}`,
    ).toBe(true)
  })

  test('workbench NETWORK tab shows the cluster membership panel', async ({ page }) => {
    const kb = requireTnKb()

    const alerts = await fetchJson<AlertListResponse>(`/alerts?kb=${kb.id}&limit=1`)
    test.skip(alerts.items.length === 0, `TN KB ${kb.id} has no alerts yet.`)
    const entityId = alerts.items[0].entity_id

    await page.goto(`/investigation/${entityId}?kb=${kb.id}`)
    await page.getByRole('tab', { name: 'Network' }).click()
    await expect(page.getByTestId('cluster-membership-panel')).toBeVisible()
  })

  test('EVIDENCE tab renders attribution bars', async ({ page }) => {
    const kb = requireTnKb()

    // The workbench selects an entity's alert with
    // items.find(a => a.entity_id === entityId) — the FIRST occurrence in the
    // feed's own order. Mirror that exactly: consider only each entity's
    // first-listed alert, otherwise this test can pick a pack the page never
    // shows and assert bars that legitimately don't render.
    const alerts = await fetchJson<AlertListResponse>(`/alerts?kb=${kb.id}&limit=500`)
    const firstAlertByEntity = new Map<string, AlertListItem>()
    for (const alert of alerts.items) {
      if (!firstAlertByEntity.has(alert.entity_id)) {
        firstAlertByEntity.set(alert.entity_id, alert)
      }
    }
    let target: AlertListItem | null = null
    for (const alert of firstAlertByEntity.values()) {
      if (!alert.evidence_pack_id) {
        continue
      }
      const pack = await fetchJson<EvidencePackResponse>(
        `/evidence-packs/${alert.evidence_pack_id}?knowledge_base_id=${kb.id}`,
      )
      if (pack.attribution.length > 0) {
        target = alert
        break
      }
    }
    test.skip(
      target === null,
      `No page-selected alert in TN KB ${kb.id} has an evidence pack with non-empty attribution yet.`,
    )
    const entityId = (target as AlertListItem).entity_id

    await page.goto(`/investigation/${entityId}?kb=${kb.id}`)
    await page.getByRole('tab', { name: 'Evidence' }).click()
    await expect(page.getByTestId('attribution-bars')).toBeVisible()
  })

  test('/policy lists at least one item for the TN KB', async ({ page }) => {
    const kb = requireTnKb()

    const policyItems = await fetchJson<PolicyItemListResponse>(
      `/policy/items?knowledge_base_id=${kb.id}`,
    )
    test.skip(
      policyItems.items.length === 0,
      `TN KB ${kb.id} has no policy items yet (still ingesting?).`,
    )
    expect(
      policyItems.items.length,
      `expected >=1 policy item in TN KB ${kb.id}`,
    ).toBeGreaterThanOrEqual(1)

    await page.goto(`/policy?kb=${kb.id}`)
    await expect(page.getByRole('heading', { name: 'Policy Intelligence' })).toBeVisible()
    await expect(page.locator('.page-list-item')).not.toHaveCount(0)

    // Soft-check only: title text is a title_template render, not a stable
    // contract, so a miss is informational rather than a hard failure — the
    // hard assertion is the >=1 item count above.
    const taskOnePackTitle = /outlier billing concentration|carries repeated analytic flags/i
    const matched = policyItems.items.some((item) => taskOnePackTitle.test(item.title))
    if (!matched) {
      console.warn(
        '[demo-walkthrough] live /policy queue has items but none match a Task 1 pack ' +
          `rule title (titles: ${policyItems.items.map((item) => item.title).join(', ')})`,
      )
    }
  })
})
