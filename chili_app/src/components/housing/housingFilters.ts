import type { HousingInstallationResponse } from '../../api/contracts'
import { normalizeBranch, type InstallationBranch } from './installationMapGeometry'

export type InstallationStatus = HousingInstallationResponse['status']

export type HousingFilterState = {
  statuses: InstallationStatus[]
  branches: InstallationBranch[]
  commands: string[]
}

export const EMPTY_HOUSING_FILTERS: HousingFilterState = {
  statuses: [],
  branches: [],
  commands: [],
}

export const INSTALLATION_STATUSES: readonly InstallationStatus[] = [
  'critical',
  'watch',
  'ok',
  'unknown',
]

export const INSTALLATION_BRANCHES: readonly InstallationBranch[] = ['USAF', 'USSF']

export function hasActiveHousingFilters(filters: HousingFilterState): boolean {
  return filters.statuses.length > 0 || filters.branches.length > 0 || filters.commands.length > 0
}

/** Immutable toggle used by every filter group: add when absent, remove when present. */
export function toggleFilterValue<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((entry) => entry !== value) : [...values, value]
}

/** Distinct commands (MAJCOM/field command) present in the loaded set, sorted for stable UI. */
export function commandOptions(installations: HousingInstallationResponse[]): string[] {
  const commands = new Set<string>()
  for (const installation of installations) {
    if (installation.majcom) {
      commands.add(installation.majcom)
    }
  }
  return [...commands].sort((left, right) => left.localeCompare(right))
}

/**
 * Apply the filter strip to the loaded set. Empty selection within a category
 * means "all"; selections within a category are OR-ed, categories are AND-ed.
 * Installations missing a branch or command are excluded once that category
 * has an active selection — an unknown branch cannot satisfy a branch filter.
 */
export function filterInstallations(
  installations: HousingInstallationResponse[],
  filters: HousingFilterState,
): HousingInstallationResponse[] {
  if (!hasActiveHousingFilters(filters)) {
    return installations
  }
  return installations.filter((installation) => {
    if (filters.statuses.length > 0 && !filters.statuses.includes(installation.status)) {
      return false
    }
    if (filters.branches.length > 0) {
      const branch = normalizeBranch(installation.branch)
      if (branch === null || !filters.branches.includes(branch)) {
        return false
      }
    }
    if (filters.commands.length > 0) {
      if (!installation.majcom || !filters.commands.includes(installation.majcom)) {
        return false
      }
    }
    return true
  })
}

export function countInstallationsByStatus(
  installations: HousingInstallationResponse[],
): Record<InstallationStatus, number> {
  const counts: Record<InstallationStatus, number> = { ok: 0, watch: 0, critical: 0, unknown: 0 }
  for (const installation of installations) {
    counts[installation.status] += 1
  }
  return counts
}

export type InstallationRank = {
  rank: number
  total: number
}

/**
 * Whether an installation reports housing data. The backend assigns
 * `open_work_orders_rank` to every reporter and `unknown` status only to
 * non-reporters, so either signal identifies a reporter; the status check
 * keeps the answer correct against older API builds that omit the rank.
 */
export function isReportingInstallation(installation: HousingInstallationResponse): boolean {
  return installation.open_work_orders_rank != null || installation.status !== 'unknown'
}

/**
 * Client-side fallback rank by open work orders (most work orders = rank 1)
 * among REPORTING installations only — non-reporters carry no work-order data
 * and must not inflate the denominator. Ties share a rank: one plus the count
 * of reporters with strictly more open work orders. Ranked against the full
 * loaded set, never the filtered subset, so the number is stable while
 * filtering.
 */
export function installationRank(
  installations: HousingInstallationResponse[],
  installationId: string,
): InstallationRank | null {
  const subject = installations.find(
    (installation) => installation.installation_id === installationId,
  )
  if (!subject || !isReportingInstallation(subject)) {
    return null
  }
  const reporters = installations.filter(isReportingInstallation)
  const higher = reporters.filter(
    (installation) => installation.open_work_orders > subject.open_work_orders,
  ).length
  return { rank: higher + 1, total: reporters.length }
}

/**
 * Rank used by the detail card. Prefers the backend-computed
 * `open_work_orders_rank` (competition rank among reporting installations —
 * authoritative because the backend sees the full reporting set) and falls
 * back to the client-side computation for older API builds that omit it.
 * The denominator counts reporters only in both paths, matching the backend
 * rank's population.
 */
export function resolveInstallationRank(
  installations: HousingInstallationResponse[],
  installation: HousingInstallationResponse,
): InstallationRank | null {
  if (installation.open_work_orders_rank != null) {
    return {
      rank: installation.open_work_orders_rank,
      total: installations.filter(isReportingInstallation).length,
    }
  }
  return installationRank(installations, installation.installation_id)
}

/**
 * Null-safe read of the API's `status_reasons` explanation list. Validated at
 * runtime (not just trusted from the contract) so the dashboard renders
 * cleanly against older API builds that omit or malform the field.
 */
export function readStatusReasons(installation: HousingInstallationResponse): string[] {
  const candidate: unknown = installation.status_reasons
  if (!Array.isArray(candidate)) {
    return []
  }
  return candidate.filter((reason): reason is string => typeof reason === 'string')
}

export type HousingAggregates = {
  totalCount: number
  reportingCount: number
  openWorkOrders: number
  criticalCount: number
  /** Unit-weighted occupancy in [0, 1]; null when no installation in the set
   * reports both an occupancy rate and a positive unit weight. */
  occupancyRate: number | null
  /** Available-unit-weighted condition index (0-100 scale); null when
   * unreported for the whole set. */
  conditionIndex: number | null
  /** Resident satisfaction score; weighted mean when the API exposes a
   * per-installation weight, plain mean of reporters otherwise. */
  residentSatisfaction: number | null
  /** Σ overdue / Σ open work orders in [0, 1]; null when no installation in
   * the set reports overdue counts or no open work orders exist. */
  overdueWorkOrderRate: number | null
  /** Σ UH available units / Σ unaccompanied authorized; null without both an
   * inventory reporter and positive authorized demand in the set. */
  uhSupplyRatio: number | null
  /** Σ MFH available units / Σ accompanied authorized; same null semantics. */
  mfhSupplyRatio: number | null
}

type WeightedPair = { value: number; weight: number }

function weightedMean(pairs: WeightedPair[]): number | null {
  let weightedSum = 0
  let weightTotal = 0
  for (const { value, weight } of pairs) {
    if (weight > 0) {
      weightedSum += value * weight
      weightTotal += weight
    }
  }
  return weightTotal > 0 ? weightedSum / weightTotal : null
}

type RatioAccumulator = { numerator: number; denominator: number; hasReporter: boolean }

function accumulateRatio(
  accumulator: RatioAccumulator,
  numerator: number | null,
  denominator: number | null,
): void {
  if (numerator != null) {
    accumulator.numerator += numerator
    accumulator.hasReporter = true
  }
  if (denominator != null) {
    accumulator.denominator += denominator
  }
}

/** Ratio only when the subset has at least one supply reporter AND observed
 * demand — zero recorded supply is a real fail, absent data is "n/a"
 * (mirrors the read model's `has_*_inventory` guards). */
function resolveRatio(accumulator: RatioAccumulator): number | null {
  return accumulator.hasReporter && accumulator.denominator > 0
    ? accumulator.numerator / accumulator.denominator
    : null
}

/**
 * Recompute the /housing/overview portfolio aggregates for an arbitrary
 * (typically filtered) installation subset, using the documented per-field
 * formulas of the backend read model (`api/_housing_read_model.py`, pinned
 * by its router test against the overview endpoint):
 *
 * - occupancy: Σ(occupancy_rate · occupancy_unit_weight) / Σ(occupancy_unit_weight)
 * - condition: Σ(condition_index · condition_unit_weight) / Σ(condition_unit_weight)
 * - satisfaction: Σ(resident_satisfaction · satisfaction_survey_count)
 *   / Σ(satisfaction_survey_count) — the flat mean across every survey value
 * - overdue rate: Σ(overdue_work_orders) / Σ(open_work_orders), unknown when
 *   the subset has no open work orders
 * - supply ratios: Σ(available) / Σ(authorized) per UH/MFH category, unknown
 *   unless authorized demand is positive AND at least one installation in the
 *   subset reported inventory (zero recorded supply is a real fail; absent
 *   inventory data is unknown, not zero)
 * - counts: reporters, open work orders, and critical installations
 *
 * With the full unfiltered set these reproduce the overview endpoint's
 * portfolio summary and executive KPI values (pinned by unit test). Metrics
 * with no reporters in the subset resolve to null — the band shows "n/a",
 * never 0 and never NaN.
 */
export function aggregateInstallations(
  installations: HousingInstallationResponse[],
): HousingAggregates {
  const occupancyPairs: WeightedPair[] = []
  const conditionPairs: WeightedPair[] = []
  const satisfactionPairs: WeightedPair[] = []
  const uhSupply: RatioAccumulator = { numerator: 0, denominator: 0, hasReporter: false }
  const mfhSupply: RatioAccumulator = { numerator: 0, denominator: 0, hasReporter: false }
  let openWorkOrders = 0
  let overdueWorkOrders = 0

  for (const installation of installations) {
    openWorkOrders += installation.open_work_orders
    overdueWorkOrders += installation.overdue_work_orders

    if (installation.occupancy_rate != null && installation.occupancy_unit_weight != null) {
      occupancyPairs.push({
        value: installation.occupancy_rate,
        weight: installation.occupancy_unit_weight,
      })
    }

    if (installation.condition_index != null && installation.condition_unit_weight != null) {
      conditionPairs.push({
        value: installation.condition_index,
        weight: installation.condition_unit_weight,
      })
    }

    if (installation.resident_satisfaction != null) {
      satisfactionPairs.push({
        value: installation.resident_satisfaction,
        weight: installation.satisfaction_survey_count,
      })
    }

    accumulateRatio(uhSupply, installation.uh_available_units ?? null, installation.uh_authorized_units)
    accumulateRatio(
      mfhSupply,
      installation.mfh_available_units ?? null,
      installation.mfh_authorized_units,
    )
  }

  return {
    totalCount: installations.length,
    reportingCount: installations.filter(isReportingInstallation).length,
    openWorkOrders,
    criticalCount: countInstallationsByStatus(installations).critical,
    occupancyRate: weightedMean(occupancyPairs),
    conditionIndex: weightedMean(conditionPairs),
    residentSatisfaction: weightedMean(satisfactionPairs),
    overdueWorkOrderRate: openWorkOrders > 0 ? overdueWorkOrders / openWorkOrders : null,
    uhSupplyRatio: resolveRatio(uhSupply),
    mfhSupplyRatio: resolveRatio(mfhSupply),
  }
}
