/**
 * Air Force Housing Scorecards (full stack). The dashboard route renders the
 * map-led executive operating picture with a single filter-driven summary band
 * above the map through the real API. The suite probes
 * GET /housing/installations (real backend, no mocking) to decide which mode
 * the stack is serving:
 *
 * - reference mode (no housing rows ingested — the default e2e stack seeds the
 *   medicare scenario via /admin/dev-seed): the page renders the 65-entry
 *   public CONUS installation reference layer with placeholder band cards, and
 *   the assertions pin that exact shape;
 * - live mode (housing pack active + `make seed-housing` run): the page
 *   renders computed installation health, the band recomputes every portfolio
 *   aggregate from the filtered installation set with the backend read model's
 *   weighting semantics, and the assertions pin both the
 *   markers-plus-pending accounting invariant and the band values against the
 *   API payload.
 *
 * Scorecard generation has no UI surface anymore (the Generate button was
 * retired 2026-07-07): runs are created through POST /scorecards/runs by the
 * seed tool (`make seed-housing SEED_ARGS="--scorecards"`) and the endpoint is
 * covered by the backend router tests. Run VIEWING stays covered here and in
 * air-force-housing-context.spec.ts via the installation-detail run links.
 *
 * All tests are read-only against the shared seeded scenario.
 */
import { expect, test } from '@playwright/test'

import { useDomainPack } from './helpers/domainPack'

const API = process.env['E2E_API_URL'] ?? 'http://localhost:8000'

/** Public reference layer size (src/data/airForceInstallations.ts). */
const REFERENCE_INSTALLATION_COUNT = 65
/** CONUS state shapes: 48 states + DC (us-atlas states-albers-10m minus AK/HI). */
const CONUS_STATE_SHAPE_COUNT = 49

type InstallationStatus = 'ok' | 'watch' | 'critical' | 'unknown'

/**
 * The installation row fields the summary band consumes — the aggregate-input
 * fields are additive on HousingInstallationResponse (see
 * backend/api/contracts.py for each field's documented weighting role).
 */
type HousingInstallationItem = {
  installation_id: string
  name: string
  status: InstallationStatus
  open_work_orders: number
  overdue_work_orders: number
  open_work_orders_rank?: number | null
  occupancy_rate?: number | null
  occupancy_unit_weight?: number | null
  condition_index?: number | null
  condition_unit_weight?: number | null
  resident_satisfaction?: number | null
  satisfaction_survey_count?: number
  uh_available_units?: number | null
  uh_authorized_units?: number
  mfh_available_units?: number | null
  mfh_authorized_units?: number
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

/** Live-mode band card labels in render order (HousingSummaryBand). */
const BAND_LABELS = [
  'Reporting',
  'Open WOs',
  'Critical',
  'Occupancy',
  'Condition index',
  'Satisfaction',
  'Overdue WO rate',
  'UH supply ratio',
  'MFH supply ratio',
] as const

type BandLabel = (typeof BAND_LABELS)[number]

/** Mirror of housingFilters.isReportingInstallation. */
function isReporting(item: HousingInstallationItem): boolean {
  return item.open_work_orders_rank != null || item.status !== 'unknown'
}

function formatFraction(value: number | null): string {
  return value == null ? 'n/a' : `${Math.round(value * 100)}%`
}

function formatScore(value: number | null): string {
  return value == null ? 'n/a' : value.toFixed(1)
}

function formatRatio(value: number | null): string {
  return value == null ? 'n/a' : value.toFixed(2)
}

/**
 * Recompute the expected band card values for an installation subset straight
 * from the API payload, mirroring housingFilters.aggregateInstallations (which
 * itself mirrors the backend read model's documented formulas, pinned by
 * backend/tests/api/test_housing_router.py against /housing/overview):
 * unit-weighted occupancy/condition, survey-weighted satisfaction,
 * Σoverdue/Σopen, Σavailable/Σauthorized supply ratios gated on a reporter
 * plus positive demand, and honest "n/a" when the subset has no reporters.
 */
function bandExpectations(items: HousingInstallationItem[]): Record<BandLabel, string> {
  let open = 0
  let overdue = 0
  let occupancyNum = 0
  let occupancyDen = 0
  let conditionNum = 0
  let conditionDen = 0
  let satisfactionNum = 0
  let satisfactionDen = 0
  let uhAvailable = 0
  let uhAuthorized = 0
  let uhHasReporter = false
  let mfhAvailable = 0
  let mfhAuthorized = 0
  let mfhHasReporter = false

  for (const item of items) {
    open += item.open_work_orders
    overdue += item.overdue_work_orders
    if (
      item.occupancy_rate != null &&
      item.occupancy_unit_weight != null &&
      item.occupancy_unit_weight > 0
    ) {
      occupancyNum += item.occupancy_rate * item.occupancy_unit_weight
      occupancyDen += item.occupancy_unit_weight
    }
    if (
      item.condition_index != null &&
      item.condition_unit_weight != null &&
      item.condition_unit_weight > 0
    ) {
      conditionNum += item.condition_index * item.condition_unit_weight
      conditionDen += item.condition_unit_weight
    }
    const surveys = item.satisfaction_survey_count ?? 0
    if (item.resident_satisfaction != null && surveys > 0) {
      satisfactionNum += item.resident_satisfaction * surveys
      satisfactionDen += surveys
    }
    if (item.uh_available_units != null) {
      uhAvailable += item.uh_available_units
      uhHasReporter = true
    }
    uhAuthorized += item.uh_authorized_units ?? 0
    if (item.mfh_available_units != null) {
      mfhAvailable += item.mfh_available_units
      mfhHasReporter = true
    }
    mfhAuthorized += item.mfh_authorized_units ?? 0
  }

  return {
    Reporting: `${items.filter(isReporting).length}/${items.length}`,
    'Open WOs': String(open),
    Critical: String(items.filter((item) => item.status === 'critical').length),
    Occupancy: formatFraction(occupancyDen > 0 ? occupancyNum / occupancyDen : null),
    'Condition index': formatScore(conditionDen > 0 ? conditionNum / conditionDen : null),
    Satisfaction: formatScore(satisfactionDen > 0 ? satisfactionNum / satisfactionDen : null),
    'Overdue WO rate': formatFraction(open > 0 ? overdue / open : null),
    'UH supply ratio': formatRatio(
      uhHasReporter && uhAuthorized > 0 ? uhAvailable / uhAuthorized : null,
    ),
    'MFH supply ratio': formatRatio(
      mfhHasReporter && mfhAuthorized > 0 ? mfhAvailable / mfhAuthorized : null,
    ),
  }
}

let restorePack: (() => Promise<void>) | null = null

// /housing belongs to the housing pack; since UXA-103 the SPA refuses routes
// the active pack does not declare, so this suite runs under that pack and
// restores the stack afterwards.
test.beforeAll(async () => {
  restorePack = await useDomainPack('department_air_force_housing')
  const res = await fetch(`${API}/housing/installations`)
  if (!res.ok) {
    throw new Error(`GET /housing/installations failed (${res.status}): ${await res.text()}`)
  }
  housing = (await res.json()) as HousingInstallationsPayload
  referenceMode = housing.items.length === 0
})

test.describe('Air Force Housing Scorecards', () => {
  test('renders the map-led dashboard with the summary band above the map', async ({ page }) => {
    await page.goto('/housing')

    await expect(page.getByRole('heading', { name: 'Housing Supply Health' })).toBeVisible()
    const band = page.getByRole('group', { name: 'Housing portfolio summary' })
    const map = page.getByRole('img', { name: 'Installation health map' })
    await expect(band).toBeVisible()
    await expect(map).toBeVisible()

    // The band renders ABOVE the map — one unified aggregate surface.
    const bandBox = await band.boundingBox()
    const mapBox = await map.boundingBox()
    expect(bandBox).not.toBeNull()
    expect(mapBox).not.toBeNull()
    expect((bandBox as { y: number }).y).toBeLessThan((mapBox as { y: number }).y)
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

  test('the generation UI is retired and the band follows the stack mode', async ({ page }) => {
    await page.goto('/housing')

    const band = page.getByRole('group', { name: 'Housing portfolio summary' })
    await expect(band).toBeVisible()

    // The Generate scorecard button is gone in BOTH modes: generation lives at
    // the API only (POST /scorecards/runs — backend router tests + the
    // `make seed-housing SEED_ARGS="--scorecards"` seed tool). The viewer
    // stays reachable from the installation-detail run links.
    await expect(page.getByRole('button', { name: /Generate scorecard|Generating/ })).toHaveCount(0)

    if (referenceMode) {
      // Without ingested housing feeds the reference banner is up, the band
      // renders placeholder cards (no fabricated numbers), and the detail card
      // states the statutory-feed requirement honestly.
      await expect(page.getByText('Public installation reference').first()).toBeVisible()
      await expect(
        page.getByText(`${REFERENCE_INSTALLATION_COUNT} public locations`),
      ).toBeVisible()
      await expect(band.locator('.housing-kpi')).toHaveCount(4)
      await expect(
        band.locator('.housing-kpi').filter({ hasText: 'Public locations' }).locator('strong'),
      ).toHaveText(String(REFERENCE_INSTALLATION_COUNT))
      await expect(
        band.locator('.housing-kpi').filter({ hasText: 'Scorecards' }).locator('strong'),
      ).toHaveText('pending')
      await expect(
        page
          .getByText(
            'Load UMD, BAH, inventory, market, and demographics feeds before generating NDAA scorecards.',
          )
          .first(),
      ).toBeVisible()
    } else {
      // Live mode: the reference banner is gone and every band card matches
      // the aggregate recomputed from the REAL /housing/installations payload
      // with the backend's weighting semantics (live parity, unfiltered).
      await expect(page.getByText('Public installation reference')).toHaveCount(0)
      // exact: the filter strip's aria-live "Showing all N installations"
      // otherwise also matches this substring.
      await expect(page.getByText(`${housing.total} installations`, { exact: true })).toBeVisible()
      await expect(band.locator('.housing-kpi')).toHaveCount(BAND_LABELS.length)
      const expected = bandExpectations(housing.items)
      for (const label of BAND_LABELS) {
        await expect(
          band.locator('.housing-kpi').filter({ hasText: label }).locator('strong'),
        ).toHaveText(expected[label])
      }
    }
  })

  test('status filter drives the summary band aggregates and clear restores them', async ({
    page,
  }) => {
    await page.goto('/housing')

    const band = page.getByRole('group', { name: 'Housing portfolio summary' })
    const statusFilters = page.getByRole('group', { name: 'Filter by status' })
    await expect(band).toBeVisible()

    if (referenceMode) {
      // Reference rows are all status "unknown": the placeholder band still
      // follows the filters — critical narrows the public-locations count to
      // zero and clearing restores it.
      const publicLocations = band
        .locator('.housing-kpi')
        .filter({ hasText: 'Public locations' })
        .locator('strong')
      await expect(publicLocations).toHaveText(String(REFERENCE_INSTALLATION_COUNT))
      await statusFilters.getByRole('button', { name: 'critical', exact: true }).click()
      await expect(publicLocations).toHaveText('0')
      await page.getByRole('button', { name: 'Clear filters' }).click()
      await expect(publicLocations).toHaveText(String(REFERENCE_INSTALLATION_COUNT))
      return
    }

    // Pick the least-populated non-empty status so the filter genuinely
    // narrows the portfolio; the seeded demo always mixes statuses.
    const counts: Record<InstallationStatus, number> = { ok: 0, watch: 0, critical: 0, unknown: 0 }
    for (const item of housing.items) {
      counts[item.status] += 1
    }
    const target = (['critical', 'watch', 'ok', 'unknown'] as const)
      .filter((status) => counts[status] > 0)
      .sort((left, right) => counts[left] - counts[right])[0]
    expect(
      counts[target],
      'live mode must mix statuses so a status filter narrows the portfolio',
    ).toBeLessThan(housing.items.length)

    const full = bandExpectations(housing.items)
    const subset = bandExpectations(housing.items.filter((item) => item.status === target))
    const changed = BAND_LABELS.filter((label) => full[label] !== subset[label])
    // The Reporting denominator always shrinks with a proper subset; the seed
    // guarantees at least one weighted aggregate moves too.
    expect(
      changed.length,
      `filtering to "${target}" must change at least two band values (changed: ${changed.join(', ')})`,
    ).toBeGreaterThanOrEqual(2)

    const cardValue = (label: BandLabel) =>
      band.locator('.housing-kpi').filter({ hasText: label }).locator('strong')

    for (const label of BAND_LABELS) {
      await expect(cardValue(label)).toHaveText(full[label])
    }

    await statusFilters.getByRole('button', { name: target, exact: true }).click()
    for (const label of BAND_LABELS) {
      await expect(cardValue(label)).toHaveText(subset[label])
    }

    await page.getByRole('button', { name: 'Clear filters' }).click()
    for (const label of BAND_LABELS) {
      await expect(cardValue(label)).toHaveText(full[label])
    }
  })
})

test.afterAll(async () => {
  if (restorePack) {
    await restorePack()
    restorePack = null
  }
})
