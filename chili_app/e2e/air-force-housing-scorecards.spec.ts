/**
 * Air Force Housing Scorecards (full stack). The dashboard route renders the
 * map-led executive operating picture and scorecard action surface through the
 * real API. The suite probes GET /housing/installations (real backend, no
 * mocking) to decide which mode the stack is serving:
 *
 * - reference mode (no housing rows ingested — the default e2e stack seeds the
 *   medicare scenario via /admin/dev-seed): the page renders the 65-entry
 *   public CONUS installation reference layer with generation gated off, and
 *   the assertions pin that exact shape;
 * - live mode (housing pack active + `make seed-housing` run): the page
 *   renders computed installation health, and the assertions pin the
 *   markers-plus-pending accounting invariant against the API payload.
 *
 * All tests are read-only against the shared seeded scenario except the
 * live-mode generation test, which creates a scorecard run through the real
 * API (append-only; safe within the serial suite).
 */
import { expect, test } from '@playwright/test'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

/** Public reference layer size (src/data/airForceInstallations.ts). */
const REFERENCE_INSTALLATION_COUNT = 65
/** CONUS state shapes: 48 states + DC (us-atlas states-albers-10m minus AK/HI). */
const CONUS_STATE_SHAPE_COUNT = 49

type HousingInstallationItem = {
  installation_id: string
  name: string
  status: 'ok' | 'watch' | 'critical' | 'unknown'
}

type HousingInstallationsPayload = {
  total: number
  items: HousingInstallationItem[]
  map_points: { installation_id: string; name: string }[]
}

let housing: HousingInstallationsPayload
let referenceMode: boolean

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function markerFor(name: string) {
  return new RegExp(`^Select ${escapeRegExp(name)} on map`)
}

test.beforeAll(async () => {
  const res = await fetch(`${API}/housing/installations`)
  if (!res.ok) {
    throw new Error(`GET /housing/installations failed (${res.status}): ${await res.text()}`)
  }
  housing = (await res.json()) as HousingInstallationsPayload
  referenceMode = housing.items.length === 0
})

test.describe('Air Force Housing Scorecards', () => {
  test('renders the map-led dashboard and scorecard action surface', async ({ page }) => {
    await page.goto('/housing')

    await expect(page.getByRole('heading', { name: 'Housing Supply Health' })).toBeVisible()
    await expect(page.getByRole('img', { name: 'Installation health map' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Generate scorecard' })).toBeVisible()
  })

  test('draws real CONUS geography inside the map svg', async ({ page }) => {
    await page.goto('/housing')

    const map = page.getByRole('img', { name: 'Installation health map' })
    await expect(map).toBeVisible()
    // Real Albers-projected state polygons, one path per CONUS state + DC.
    await expect(map.locator('path[data-state]')).toHaveCount(CONUS_STATE_SHAPE_COUNT)
    await expect(map.locator('path[data-state="48"]')).toHaveAttribute('d', /.+/) // Texas
  })

  test('plots every installation as an accessible marker or pending entry', async ({ page }) => {
    await page.goto('/housing')

    const markers = page.getByRole('button', { name: /^Select .+ on map/ })
    const pendingGroup = page.getByRole('group', { name: 'Installations with location pending' })

    if (referenceMode) {
      // All 65 public reference installations carry CONUS coordinates, so all
      // plot and the location-pending list must not appear.
      await expect(markers).toHaveCount(REFERENCE_INSTALLATION_COUNT)
      await expect(pendingGroup).toHaveCount(0)
      // Reference markers carry the unknown-status styling contract.
      await expect(markers.first()).toHaveAttribute('data-status', 'unknown')
    } else {
      // Live mode invariant: nothing is silently dropped — every installation
      // row is either a plotted marker or a visible location-pending entry.
      await expect(markers).toHaveCount(housing.map_points.length)
      const pendingCount = housing.items.length - housing.map_points.length
      if (pendingCount > 0) {
        await expect(pendingGroup).toBeVisible()
        await expect(pendingGroup.locator('li')).toHaveCount(pendingCount)
      } else {
        await expect(pendingGroup).toHaveCount(0)
      }
    }
  })

  test('marker selection drives the detail panel and URL param', async ({ page }) => {
    await page.goto('/housing')

    // Live targets must come from map_points — only plotted installations have
    // a marker to click. The reference layer always plots minot_afb.
    const livePoint = housing.map_points[housing.map_points.length - 1]
    const targetName = referenceMode ? 'Minot AFB' : livePoint.name
    const targetId = referenceMode ? 'minot_afb' : livePoint.installation_id

    const marker = page.getByRole('button', { name: markerFor(targetName) })
    // Hover surfaces the tooltip before selection.
    await marker.hover()
    await expect(page.getByTestId('map-tooltip')).toContainText(targetName)

    await marker.click()
    await expect(page).toHaveURL(new RegExp(`installation=${targetId}`))
    await expect(marker).toHaveAttribute('aria-pressed', 'true')

    const detail = page.locator('section[aria-label="Installation detail"]')
    await expect(detail.locator('.housing-detail-title')).toHaveText(targetName)
  })

  test('deep link ?installation= preselects the installation', async ({ page }) => {
    const livePoint = housing.map_points[0]
    const targetName = referenceMode ? 'Vandenberg SFB' : livePoint.name
    const targetId = referenceMode ? 'vandenberg_sfb' : livePoint.installation_id

    await page.goto(`/housing?installation=${targetId}`)

    const detail = page.locator('section[aria-label="Installation detail"]')
    await expect(detail.locator('.housing-detail-title')).toHaveText(targetName)
    await expect(page.getByRole('button', { name: markerFor(targetName) })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  test('scorecard generation follows the stack mode', async ({ page }) => {
    await page.goto('/housing')

    const generate = page.getByRole('button', { name: /Generate scorecard|Generating/ })
    await expect(generate).toBeVisible()

    if (referenceMode) {
      // Without ingested housing feeds the reference banner is up and
      // generation is honestly gated off with the statutory-feed reason.
      await expect(page.getByText('Public installation reference').first()).toBeVisible()
      await expect(
        page.getByText(`${REFERENCE_INSTALLATION_COUNT} public locations`),
      ).toBeVisible()
      await expect(generate).toBeDisabled()
      await expect(
        page
          .getByText(
            'Load UMD, BAH, inventory, market, and demographics feeds before generating NDAA scorecards.',
          )
          .first(),
      ).toBeVisible()
    } else {
      // Live mode: the reference banner is gone and generation queues a real
      // run through POST /scorecards/runs (idempotent snapshot hashing means
      // regenerating over unchanged data reuses the run).
      await expect(page.getByText('Public installation reference')).toHaveCount(0)
      // exact: the filter strip's aria-live "Showing all N installations"
      // otherwise also matches this substring.
      await expect(page.getByText(`${housing.total} installations`, { exact: true })).toBeVisible()
      await expect(generate).toBeEnabled()
      await generate.click()
      await expect(page.getByText('Scorecard generation queued.')).toBeVisible()

      // The run is really listed in the run store for the page's
      // default-selected installation (items[0]).
      const kbRes = await fetch(`${API}/knowledgebases`)
      expect(kbRes.ok).toBe(true)
      const kbs = (await kbRes.json()) as {
        items: { id: string; status: string; created_at: string }[]
      }
      const candidates = kbs.items.filter((kb) => kb.status === 'ready' || kb.status === 'active')
      expect(candidates.length).toBeGreaterThan(0)
      const kbId = candidates
        .sort(
          (a, b) =>
            Number(b.status === 'ready') - Number(a.status === 'ready') ||
            b.created_at.localeCompare(a.created_at),
        )[0]
        .id
      const runsRes = await fetch(
        `${API}/scorecards/runs?knowledge_base_id=${kbId}&limit=500`,
      )
      expect(runsRes.ok).toBe(true)
      const runs = (await runsRes.json()) as {
        items: { scope_type: string; scope_id: string; status: string }[]
      }
      const targetId = housing.items[0].installation_id
      expect(
        runs.items.some(
          (run) =>
            run.scope_type === 'installation' &&
            run.scope_id === targetId &&
            run.status === 'generated',
        ),
      ).toBe(true)
    }
  })
})
