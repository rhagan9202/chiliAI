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
