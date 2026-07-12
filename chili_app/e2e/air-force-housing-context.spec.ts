/**
 * Air Force Housing — scorecard viewer, dashboard context, and filters
 * (full stack). Sibling to air-force-housing-scorecards.spec.ts: the suite
 * probes GET /housing/installations (real backend, no mocking) to decide which
 * mode the stack is serving and adapts its assertions:
 *
 * - reference mode (no housing rows ingested — the default e2e stack seeds the
 *   medicare scenario via /admin/dev-seed): the viewer's guarded states are
 *   exercised directly by URL, the filter strip narrows the 65-entry public
 *   reference layer to zero rows and restores it, and the live-only surfaces
 *   ("Why this status", scorecard run links) are asserted absent;
 * - live mode (housing pack active + seeded demo KB): the viewer is opened
 *   from a real dashboard run link and its graded sections, metric health
 *   chips, and export downloads are pinned against the run's API payload; the
 *   filter strip narrows map markers, ranking rows, and status counts
 *   consistently; "Why this status" renders the API's status_reasons verbatim.
 *
 * All tests are read-only against the shared seeded scenario. No KB id is
 * pinned — knowledge bases are resolved the same way the dashboard resolves
 * them (ready-first, newest created_at, cleanup-pending excluded).
 */
import { expect, test } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

/** Public reference layer size (src/data/airForceInstallations.ts). */
const REFERENCE_INSTALLATION_COUNT = 65

type InstallationStatus = 'ok' | 'watch' | 'critical' | 'unknown'

type HousingInstallationItem = {
  installation_id: string
  name: string
  status: InstallationStatus
  status_reasons?: string[]
  open_work_orders: number
}

type HousingInstallationsPayload = {
  total: number
  items: HousingInstallationItem[]
  map_points: { installation_id: string; name: string }[]
}

type KnowledgeBaseItem = {
  id: string
  name: string
  status: string
  created_at: string
  domain?: string | null
  pending_cleanup?: boolean
}

type ScorecardRunSummary = {
  id: string
  template_id: string
  template_name: string
  scope_type: string
  scope_id: string
  status: 'generated' | 'failed' | 'superseded'
  overall_health: 'pass' | 'warn' | 'fail' | 'incomplete'
  created_at: string
}

type ScorecardRunDetail = ScorecardRunSummary & {
  sections: { id: string; label: string; metrics: { metric_id: string; health: string }[] }[]
}

type WorkflowItem = { id: string; workflow_type: string; status: string }

let housing: HousingInstallationsPayload
let referenceMode: boolean
let knowledgeBases: KnowledgeBaseItem[]
/** KB the dashboard resolves (mirror of api/_housing_read_model resolution). */
let activeKb: KnowledgeBaseItem | null
/** Newest installation-scoped run for activeKb (live mode only). */
let latestRun: ScorecardRunDetail | null

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) {
    throw new Error(`GET ${path} failed (${res.status}): ${await res.text()}`)
  }
  return (await res.json()) as T
}

function resolveActiveKnowledgeBase(items: KnowledgeBaseItem[]): KnowledgeBaseItem | null {
  const candidates = items.filter(
    (kb) => (kb.status === 'ready' || kb.status === 'active') && !kb.pending_cleanup,
  )
  if (candidates.length === 0) {
    return null
  }
  return candidates.reduce((best, kb) => {
    const kbReady = kb.status === 'ready'
    const bestReady = best.status === 'ready'
    if (kbReady !== bestReady) {
      return kbReady ? kb : best
    }
    return kb.created_at > best.created_at ? kb : best
  })
}

test.beforeAll(async () => {
  housing = await fetchJson<HousingInstallationsPayload>('/housing/installations')
  referenceMode = housing.items.length === 0
  knowledgeBases = (await fetchJson<{ items: KnowledgeBaseItem[] }>('/knowledgebases')).items
  activeKb = resolveActiveKnowledgeBase(knowledgeBases)
  latestRun = null

  if (!referenceMode && activeKb) {
    const runs = (
      await fetchJson<{ items: ScorecardRunSummary[] }>(
        `/scorecards/runs?knowledge_base_id=${activeKb.id}&limit=500`,
      )
    ).items
    const newest = [...runs]
      .sort((left, right) => right.created_at.localeCompare(left.created_at))
      .find((run) => run.scope_type === 'installation')
    if (newest) {
      latestRun = await fetchJson<ScorecardRunDetail>(
        `/scorecards/runs/${encodeURIComponent(newest.id)}?knowledge_base_id=${activeKb.id}`,
      )
    }
  }
})

test.describe('Scorecard run viewer', () => {
  test('guards missing knowledge base context and unknown runs honestly', async ({ page }) => {
    // Both guard states are stack-independent: they render against the real
    // API without any seeded scorecard data.
    await page.goto('/scorecards/run-that-does-not-exist')
    await expect(page.getByText('Missing knowledge base context')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Back to housing dashboard' })).toBeVisible()

    if (activeKb) {
      await page.goto(`/scorecards/run-that-does-not-exist?kb=${activeKb.id}`)
      await expect(page.getByText('Scorecard run not found')).toBeVisible()
      await expect(page.getByRole('link', { name: 'Back to housing dashboard' })).toBeVisible()
    }
  })

  test('dashboard run link opens graded sections with working exports', async ({ page }) => {
    if (referenceMode) {
      // Reference mode has no scorecard runs: the detail card must not offer
      // run links — it is the dashboard's only scorecard-viewer entry point
      // now that the readiness panel is retired.
      await page.goto('/housing')
      await expect(page.locator('.housing-detail-runs')).toHaveCount(0)
      await expect(page.locator('a.housing-run-link')).toHaveCount(0)
      return
    }

    expect(activeKb, 'live mode requires a resolvable knowledge base').not.toBeNull()
    expect(latestRun, 'live mode requires at least one installation-scoped run').not.toBeNull()
    const run = latestRun as ScorecardRunDetail
    const installationName =
      housing.items.find((item) => item.installation_id === run.scope_id)?.name ?? run.scope_id

    // The newest run overall is by construction the latest for its template
    // within its scope, so the detail card's "Scorecards" section links it.
    await page.goto(`/housing?installation=${run.scope_id}`)
    const detail = page.locator('section[aria-label="Installation detail"]')
    await expect(detail.locator('.housing-detail-title')).toHaveText(installationName)

    const runLink = detail.getByRole('link', {
      name: new RegExp(
        `^View ${escapeRegExp(run.template_name)} scorecard for ${escapeRegExp(installationName)}`,
      ),
    })
    await expect(runLink).toBeVisible()
    await runLink.click()

    await expect(page).toHaveURL(new RegExp(`/scorecards/${escapeRegExp(run.id)}\\?kb=`))
    await expect(page.getByRole('heading', { name: run.template_name })).toBeVisible()
    await expect(page.getByText(`overall ${run.overall_health}`, { exact: true })).toBeVisible()

    // Every graded section from the API payload renders as a labelled region
    // and every metric renders a row carrying a health chip.
    expect(run.sections.length).toBeGreaterThan(0)
    for (const section of run.sections) {
      await expect(page.getByRole('region', { name: section.label })).toBeVisible()
    }
    const totalMetrics = run.sections.reduce((sum, section) => sum + section.metrics.length, 0)
    expect(totalMetrics).toBeGreaterThan(0)
    await expect(page.locator('.scorecard-metric')).toHaveCount(totalMetrics)
    const firstMetric = run.sections[0].metrics[0]
    await expect(
      page
        .locator('.scorecard-metric')
        .first()
        .locator('.ui-chip', { hasText: firstMetric.health }),
    ).toBeVisible()

    // Export buttons are enabled and the JSON export produces a real download
    // through the real export endpoint.
    const downloadJson = page.getByRole('button', { name: 'Download JSON' })
    const downloadMarkdown = page.getByRole('button', { name: 'Download Markdown' })
    await expect(downloadJson).toBeEnabled()
    await expect(downloadMarkdown).toBeEnabled()

    const downloadPromise = page.waitForEvent('download')
    await downloadJson.click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`scorecard-${run.id}.json`)

    // The back link returns to the dashboard with the installation preselected.
    await page.getByRole('link', { name: `Back to ${installationName}` }).click()
    await expect(page).toHaveURL(new RegExp(`installation=${escapeRegExp(run.scope_id)}`))
    await expect(detail.locator('.housing-detail-title')).toHaveText(installationName)
  })
})

test.describe('Installation status context', () => {
  test('"Why this status" lists the API status drivers for a non-ok installation', async ({
    page,
  }) => {
    if (referenceMode) {
      // Reference rows carry no computed status, so the explanation block must
      // not render at all.
      await page.goto('/housing')
      await expect(
        page.locator('section[aria-label="Installation detail"]').getByText('Why this status'),
      ).toHaveCount(0)
      return
    }

    const flagged = housing.items.find(
      (item) =>
        (item.status === 'critical' || item.status === 'watch') &&
        (item.status_reasons?.length ?? 0) > 0,
    )
    expect(
      flagged,
      'live mode must expose at least one watch/critical installation with status_reasons',
    ).toBeTruthy()
    const target = flagged as HousingInstallationItem
    const reasons = target.status_reasons ?? []

    await page.goto(`/housing?installation=${target.installation_id}`)
    const detail = page.locator('section[aria-label="Installation detail"]')
    await expect(detail.locator('.housing-detail-title')).toHaveText(target.name)
    const reasonsBlock = detail.locator('.housing-status-reasons')
    await expect(reasonsBlock.getByText('Why this status')).toBeVisible()
    await expect(reasonsBlock.locator('li')).toHaveCount(reasons.length)
    for (const reason of reasons) {
      await expect(reasonsBlock.getByText(reason, { exact: true })).toBeVisible()
    }

    // An ok installation reports no drivers and says so honestly.
    const healthy = housing.items.find(
      (item) => item.status === 'ok' && (item.status_reasons?.length ?? 0) === 0,
    )
    if (healthy) {
      await page.goto(`/housing?installation=${healthy.installation_id}`)
      await expect(detail.locator('.housing-detail-title')).toHaveText(healthy.name)
      await expect(
        detail.getByText('No status drivers reported for this period.'),
      ).toBeVisible()
    }
  })
})

test.describe('Housing dashboard filters', () => {
  test('status filter narrows map, table, and counts together; clear restores', async ({
    page,
  }) => {
    await page.goto('/housing')

    const markers = page.getByRole('button', { name: /^Select .+ on map/ })
    const tableRows = page.locator('.housing-table tbody tr')
    const statusStrip = page.locator('[aria-label="Status counts"]')
    const statusFilters = page.getByRole('group', { name: 'Filter by status' })
    const total = referenceMode ? REFERENCE_INSTALLATION_COUNT : housing.items.length
    const totalMarkers = referenceMode ? REFERENCE_INSTALLATION_COUNT : housing.map_points.length

    await expect(page.getByText(`Showing all ${total} installations`)).toBeVisible()
    await expect(markers).toHaveCount(totalMarkers)
    await expect(tableRows).toHaveCount(total)

    if (referenceMode) {
      // Reference rows are all status "unknown": filtering to critical must
      // narrow every surface to zero and surface the empty states.
      await statusFilters.getByRole('button', { name: 'critical', exact: true }).click()
      await expect(page.getByText(`Showing 0 of ${total} installations`)).toBeVisible()
      await expect(markers).toHaveCount(0)
      await expect(tableRows).toHaveCount(0)
      await expect(page.getByText('No matching installations').first()).toBeVisible()
    } else {
      // Pick the least-populated non-empty status so the filter genuinely
      // narrows the portfolio whenever the data is mixed.
      const counts: Record<InstallationStatus, number> = {
        ok: 0,
        watch: 0,
        critical: 0,
        unknown: 0,
      }
      for (const item of housing.items) {
        counts[item.status] += 1
      }
      const target = (['critical', 'watch', 'ok', 'unknown'] as const)
        .filter((status) => counts[status] > 0)
        .sort((left, right) => counts[left] - counts[right])[0]
      const matchCount = counts[target]
      const matchIds = new Set(
        housing.items
          .filter((item) => item.status === target)
          .map((item) => item.installation_id),
      )
      const matchMarkers = housing.map_points.filter((point) =>
        matchIds.has(point.installation_id),
      ).length

      await statusFilters.getByRole('button', { name: target, exact: true }).click()
      await expect(
        page.getByText(`Showing ${matchCount} of ${total} installations`),
      ).toBeVisible()
      await expect(markers).toHaveCount(matchMarkers)
      await expect(tableRows).toHaveCount(matchCount)

      // The status strip counts only the filtered set: the selected status
      // keeps its full count, every other status drops to zero.
      for (const status of ['critical', 'watch', 'ok', 'unknown'] as const) {
        const row = statusStrip.locator('.metric-row', { hasText: status })
        await expect(row.locator('.ui-chip')).toHaveText(
          status === target ? String(matchCount) : '0',
        )
      }
    }

    await page.getByRole('button', { name: 'Clear filters' }).click()
    await expect(page.getByText(`Showing all ${total} installations`)).toBeVisible()
    await expect(markers).toHaveCount(totalMarkers)
    await expect(tableRows).toHaveCount(total)
  })
})

test.describe('Housing demo ingestion health', () => {
  test('the housing demo knowledge base has no failed ingestion runs', async () => {
    // The demo-killing bug this mission fixed surfaced as failed ingestion
    // workflows in the run timeline. Probe the REAL workflow store for every
    // housing-domain KB: none may carry a failed run, and the current demo KB
    // must have completed runs.
    const housingKbs = knowledgeBases.filter(
      (kb) =>
        kb.domain === 'department_air_force_housing' &&
        (kb.status === 'ready' || kb.status === 'active') &&
        !kb.pending_cleanup,
    )
    test.skip(housingKbs.length === 0, 'no housing-domain knowledge base on this stack')

    const failures: string[] = []
    for (const kb of housingKbs) {
      const workflows = (
        await fetchJson<{ items: WorkflowItem[] }>(
          `/workflows?knowledge_base_id=${kb.id}&limit=200`,
        )
      ).items
      for (const workflow of workflows) {
        if (workflow.status !== 'completed') {
          failures.push(
            `${kb.name} (${kb.id}): workflow ${workflow.id} [${workflow.workflow_type}] is ${workflow.status}`,
          )
        }
      }
    }
    expect(failures, failures.join('\n')).toEqual([])

    // The KB the dashboard resolves must show a real, fully completed
    // ingestion history — an empty timeline would mean the demo was seeded
    // around the pipeline instead of through it.
    const demoKb = resolveActiveKnowledgeBase(housingKbs)
    expect(demoKb).not.toBeNull()
    const demoWorkflows = (
      await fetchJson<{ items: WorkflowItem[] }>(
        `/workflows?knowledge_base_id=${(demoKb as KnowledgeBaseItem).id}&limit=200`,
      )
    ).items
    expect(demoWorkflows.length).toBeGreaterThan(0)
    expect(demoWorkflows.every((workflow) => workflow.status === 'completed')).toBe(true)
  })
})
