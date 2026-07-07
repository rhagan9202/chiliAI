import { describe, expect, it } from 'vitest'

import type { HousingInstallationResponse } from '../../../api/contracts'
import {
  aggregateInstallations,
  commandOptions,
  countInstallationsByStatus,
  EMPTY_HOUSING_FILTERS,
  filterInstallations,
  hasActiveHousingFilters,
  installationRank,
  readStatusReasons,
  resolveInstallationRank,
  toggleFilterValue,
} from '../housingFilters'

function installation(
  overrides: Partial<HousingInstallationResponse> & { installation_id: string },
): HousingInstallationResponse {
  return {
    name: overrides.installation_id,
    majcom: null,
    branch: null,
    state: null,
    status: 'unknown',
    open_work_orders: 0,
    overdue_work_orders: 0,
    satisfaction_survey_count: 0,
    uh_authorized_units: 0,
    mfh_authorized_units: 0,
    occupancy_rate: null,
    ...overrides,
  }
}

const portfolio: HousingInstallationResponse[] = [
  installation({
    installation_id: 'edwards',
    majcom: 'AFMC',
    branch: 'USAF',
    status: 'critical',
    open_work_orders: 95,
  }),
  installation({
    installation_id: 'barksdale',
    majcom: 'AFGSC',
    branch: 'USAF',
    status: 'watch',
    open_work_orders: 44,
  }),
  installation({
    installation_id: 'patrick',
    majcom: 'SSC',
    branch: 'USSF',
    status: 'ok',
    open_work_orders: 44,
  }),
  // Non-reporter: unknown status, no rank — must never count toward rank denominators.
  installation({ installation_id: 'mystery', status: 'unknown', open_work_orders: 0 }),
]

describe('toggleFilterValue', () => {
  it('adds absent values and removes present ones immutably', () => {
    const start: string[] = []
    const added = toggleFilterValue(start, 'AFMC')
    expect(added).toEqual(['AFMC'])
    expect(start).toEqual([])
    expect(toggleFilterValue(added, 'AFMC')).toEqual([])
  })
})

describe('hasActiveHousingFilters', () => {
  it('is false for the empty state and true for any selection', () => {
    expect(hasActiveHousingFilters(EMPTY_HOUSING_FILTERS)).toBe(false)
    expect(hasActiveHousingFilters({ ...EMPTY_HOUSING_FILTERS, statuses: ['ok'] })).toBe(true)
    expect(hasActiveHousingFilters({ ...EMPTY_HOUSING_FILTERS, branches: ['USSF'] })).toBe(true)
    expect(hasActiveHousingFilters({ ...EMPTY_HOUSING_FILTERS, commands: ['SSC'] })).toBe(true)
  })
})

describe('commandOptions', () => {
  it('returns distinct sorted commands, skipping installations without one', () => {
    expect(commandOptions(portfolio)).toEqual(['AFGSC', 'AFMC', 'SSC'])
  })
})

describe('filterInstallations', () => {
  it('returns the input untouched when no filters are active', () => {
    expect(filterInstallations(portfolio, EMPTY_HOUSING_FILTERS)).toBe(portfolio)
  })

  it('ORs selections within a category', () => {
    const filtered = filterInstallations(portfolio, {
      ...EMPTY_HOUSING_FILTERS,
      statuses: ['critical', 'watch'],
    })
    expect(filtered.map((entry) => entry.installation_id)).toEqual(['edwards', 'barksdale'])
  })

  it('ANDs across categories', () => {
    const filtered = filterInstallations(portfolio, {
      statuses: ['critical', 'ok'],
      branches: ['USAF'],
      commands: ['AFMC'],
    })
    expect(filtered.map((entry) => entry.installation_id)).toEqual(['edwards'])
  })

  it('excludes installations missing a branch or command once that category is active', () => {
    const byBranch = filterInstallations(portfolio, {
      ...EMPTY_HOUSING_FILTERS,
      branches: ['USAF', 'USSF'],
    })
    expect(byBranch.map((entry) => entry.installation_id)).not.toContain('mystery')

    const byCommand = filterInstallations(portfolio, {
      ...EMPTY_HOUSING_FILTERS,
      commands: ['AFGSC', 'AFMC', 'SSC'],
    })
    expect(byCommand.map((entry) => entry.installation_id)).not.toContain('mystery')
  })

  it('can produce an empty result for contradictory selections', () => {
    const filtered = filterInstallations(portfolio, {
      ...EMPTY_HOUSING_FILTERS,
      branches: ['USSF'],
      commands: ['AFMC'],
    })
    expect(filtered).toEqual([])
  })
})

describe('countInstallationsByStatus', () => {
  it('counts every status bucket over the given set', () => {
    expect(countInstallationsByStatus(portfolio)).toEqual({
      ok: 1,
      watch: 1,
      critical: 1,
      unknown: 1,
    })
    expect(countInstallationsByStatus([])).toEqual({ ok: 0, watch: 0, critical: 0, unknown: 0 })
  })
})

describe('installationRank', () => {
  it('ranks reporters by open work orders descending with shared ranks for ties', () => {
    // 4 loaded installations, but only 3 report — the denominator counts reporters.
    expect(installationRank(portfolio, 'edwards')).toEqual({ rank: 1, total: 3 })
    expect(installationRank(portfolio, 'barksdale')).toEqual({ rank: 2, total: 3 })
    expect(installationRank(portfolio, 'patrick')).toEqual({ rank: 2, total: 3 })
  })

  it('returns null for non-reporting and unknown installations', () => {
    expect(installationRank(portfolio, 'mystery')).toBeNull()
    expect(installationRank(portfolio, 'nowhere')).toBeNull()
  })
})

describe('resolveInstallationRank', () => {
  it('prefers the backend-computed rank with a reporters-only denominator', () => {
    const ranked = installation({
      installation_id: 'edwards',
      status: 'critical',
      open_work_orders: 95,
      open_work_orders_rank: 3,
    })
    // Client-side computation would say rank 1 (most open WOs in the loaded
    // set); the backend rank wins because it sees the full reporting set.
    // Total is 3, not 4: the non-reporting 'mystery' installation is excluded.
    expect(resolveInstallationRank([ranked, ...portfolio.slice(1)], ranked)).toEqual({
      rank: 3,
      total: 3,
    })
  })

  it('falls back to the client-side computation when the field is absent or null', () => {
    const unranked = installation({
      installation_id: 'edwards',
      status: 'critical',
      open_work_orders: 95,
      open_work_orders_rank: null,
    })
    expect(resolveInstallationRank([unranked, ...portfolio.slice(1)], unranked)).toEqual({
      rank: 1,
      total: 3,
    })
  })

  it('reports no rank for a non-reporting installation', () => {
    const nonReporter = portfolio[3]
    expect(resolveInstallationRank(portfolio, nonReporter)).toBeNull()
  })
})

/**
 * Mirror of the backend router test's record fixture
 * (backend/tests/api/test_housing_router.py::_installation_records) projected
 * through the per-installation aggregate fields the read model now exposes:
 * eglin (ok), edwards (watch), patrick (critical), plus a context-only
 * installation that reports nothing. Aggregating ALL of these must reproduce
 * the /housing/overview portfolio summary and executive KPI values that the
 * backend test pins on the same data — the two computations are one contract.
 */
const overviewParityPortfolio: HousingInstallationResponse[] = [
  installation({
    installation_id: 'eglin_afb',
    status: 'ok',
    open_work_orders: 30,
    overdue_work_orders: 1,
    occupancy_rate: 0.92,
    occupancy_unit_weight: 1140, // 1100 available + 40 offline
    condition_index: 88.0,
    condition_unit_weight: 1100,
    resident_satisfaction: 82.0,
    satisfaction_survey_count: 1,
    uh_available_units: 1100,
    uh_authorized_units: 1000,
    mfh_available_units: null, // MFH inventory never landed — absent, not zero
    mfh_authorized_units: 900,
  }),
  installation({
    installation_id: 'edwards_afb',
    status: 'watch',
    open_work_orders: 40,
    overdue_work_orders: 6,
    occupancy_rate: 0.8,
    occupancy_unit_weight: 1200, // 1150 + 50
    condition_index: 74.0,
    condition_unit_weight: 1150,
    resident_satisfaction: 68.0,
    satisfaction_survey_count: 1,
    uh_available_units: 1150,
    uh_authorized_units: 1200,
    mfh_available_units: null,
    mfh_authorized_units: 800,
  }),
  installation({
    installation_id: 'patrick_sfb',
    status: 'critical',
    open_work_orders: 50,
    overdue_work_orders: 20,
    occupancy_rate: 0.7,
    occupancy_unit_weight: 460, // 400 + 60
    condition_index: 65.0,
    condition_unit_weight: 400,
    resident_satisfaction: 50.0,
    satisfaction_survey_count: 1,
    uh_available_units: 400,
    uh_authorized_units: 500,
    mfh_available_units: null,
    mfh_authorized_units: 450,
  }),
  // Market-context only: no inventory or experience feeds → reports nothing.
  installation({ installation_id: 'context_only_afb' }),
]

describe('aggregateInstallations', () => {
  it('reproduces the /housing/overview values over the full unfiltered set', () => {
    const aggregates = aggregateInstallations(overviewParityPortfolio)

    expect(aggregates.totalCount).toBe(4)
    expect(aggregates.reportingCount).toBe(3)
    expect(aggregates.openWorkOrders).toBe(30 + 40 + 50)
    expect(aggregates.criticalCount).toBe(1)
    // Display-precision equality against the overview endpoint's rounded
    // payloads (occupancy 4dp, condition/ratios 3dp, satisfaction 2dp).
    expect(aggregates.occupancyRate?.toFixed(4)).toBe(
      ((0.92 * 1140 + 0.8 * 1200 + 0.7 * 460) / 2800).toFixed(4),
    )
    expect(aggregates.conditionIndex?.toFixed(3)).toBe(
      ((88.0 * 1100 + 74.0 * 1150 + 65.0 * 400) / (1100 + 1150 + 400)).toFixed(3),
    )
    expect(aggregates.residentSatisfaction?.toFixed(2)).toBe(
      ((82.0 + 68.0 + 50.0) / 3).toFixed(2),
    )
    expect(aggregates.overdueWorkOrderRate).toBeCloseTo((1 + 6 + 20) / (30 + 40 + 50), 10)
    expect(aggregates.uhSupplyRatio?.toFixed(3)).toBe(
      ((1100 + 1150 + 400) / (1000 + 1200 + 500)).toFixed(3),
    )
    // MFH inventory never landed anywhere → unknown, not fabricated.
    expect(aggregates.mfhSupplyRatio).toBeNull()
  })

  it('weights satisfaction by survey count, not equally per installation', () => {
    const heavier = {
      ...overviewParityPortfolio[0],
      resident_satisfaction: 90,
      satisfaction_survey_count: 3,
    }
    const lighter = {
      ...overviewParityPortfolio[1],
      resident_satisfaction: 50,
      satisfaction_survey_count: 1,
    }
    const aggregates = aggregateInstallations([heavier, lighter])
    // Flat mean across surveys: (90·3 + 50·1) / 4 = 80, not (90+50)/2 = 70.
    expect(aggregates.residentSatisfaction).toBeCloseTo(80, 10)
  })

  it('recomputes every aggregate for a filtered subset', () => {
    const aggregates = aggregateInstallations(
      filterInstallations(overviewParityPortfolio, {
        ...EMPTY_HOUSING_FILTERS,
        statuses: ['critical'],
      }),
    )

    expect(aggregates.totalCount).toBe(1)
    expect(aggregates.reportingCount).toBe(1)
    expect(aggregates.openWorkOrders).toBe(50)
    expect(aggregates.criticalCount).toBe(1)
    expect(aggregates.occupancyRate).toBeCloseTo(0.7, 10)
    expect(aggregates.conditionIndex).toBeCloseTo(65.0, 10)
    expect(aggregates.residentSatisfaction).toBeCloseTo(50.0, 10)
    expect(aggregates.overdueWorkOrderRate).toBeCloseTo(20 / 50, 10)
    expect(aggregates.uhSupplyRatio).toBeCloseTo(400 / 500, 10)
    expect(aggregates.mfhSupplyRatio).toBeNull()
  })

  it('resolves to null — never 0 or NaN — when the subset has no reporters for a metric', () => {
    const nonReporters = [installation({ installation_id: 'context_only_afb' })]
    const aggregates = aggregateInstallations(nonReporters)

    expect(aggregates.totalCount).toBe(1)
    expect(aggregates.reportingCount).toBe(0)
    expect(aggregates.openWorkOrders).toBe(0)
    expect(aggregates.criticalCount).toBe(0)
    expect(aggregates.occupancyRate).toBeNull()
    expect(aggregates.conditionIndex).toBeNull()
    expect(aggregates.residentSatisfaction).toBeNull()
    expect(aggregates.overdueWorkOrderRate).toBeNull()
    expect(aggregates.uhSupplyRatio).toBeNull()
    expect(aggregates.mfhSupplyRatio).toBeNull()

    expect(aggregateInstallations([]).occupancyRate).toBeNull()
    expect(aggregateInstallations([]).totalCount).toBe(0)
  })

  it('treats zero recorded supply as a real ratio, but absent inventory as unknown', () => {
    // Zero available units WITH an inventory report → honest 0.0 ratio.
    const zeroSupply = installation({
      installation_id: 'zero_supply',
      status: 'critical',
      uh_available_units: 0,
      uh_authorized_units: 500,
    })
    expect(aggregateInstallations([zeroSupply]).uhSupplyRatio).toBe(0)

    // Authorized demand but NO inventory row (null available) → unknown.
    const noInventory = installation({
      installation_id: 'no_inventory',
      status: 'watch',
      uh_available_units: null,
      uh_authorized_units: 500,
    })
    expect(aggregateInstallations([noInventory]).uhSupplyRatio).toBeNull()

    // Inventory reported but zero authorized demand → unknown (no denominator).
    const noDemand = installation({
      installation_id: 'no_demand',
      status: 'ok',
      uh_available_units: 300,
      uh_authorized_units: 0,
    })
    expect(aggregateInstallations([noDemand]).uhSupplyRatio).toBeNull()
  })
})

describe('readStatusReasons', () => {
  it('keeps only string entries from the status_reasons field', () => {
    const withReasons = {
      ...installation({ installation_id: 'edwards' }),
      status_reasons: ['Open work orders far above portfolio median', 42, null, 'Low occupancy'],
    } as unknown as HousingInstallationResponse
    expect(readStatusReasons(withReasons)).toEqual([
      'Open work orders far above portfolio median',
      'Low occupancy',
    ])
  })

  it('returns an empty list when the field is absent or malformed', () => {
    expect(readStatusReasons(installation({ installation_id: 'edwards' }))).toEqual([])
    const malformed = {
      ...installation({ installation_id: 'edwards' }),
      status_reasons: 'not-a-list',
    } as unknown as HousingInstallationResponse
    expect(readStatusReasons(malformed)).toEqual([])
  })
})
