import { describe, expect, it } from 'vitest'

import type { HousingInstallationResponse } from '../../../api/contracts'
import {
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
