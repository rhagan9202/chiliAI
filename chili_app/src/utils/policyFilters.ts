import { countLabel } from './countLabel'

/**
 * The policy-queue filter model (UXA-401).
 *
 * Unlike `caseFilters`, nothing here filters the loaded list: the policy queue
 * is paged and filtered **server-side**, so this module only owns the state and
 * its URL round-trip, and `usePolicyItems` sends it to the API. The counts
 * beside each option come from the response's `status_counts`, which the server
 * tallies over the whole knowledge base — a count computed from the filtered
 * page would drop every other option to zero the moment one was selected.
 */

export interface PolicyFilterState {
  statuses: string[]
  search: string
}

export const EMPTY_POLICY_FILTERS: PolicyFilterState = {
  statuses: [],
  search: '',
}

/** Reads only the parameters this model owns, so `?kb=` and `?item=` survive. */
export function parsePolicyFilters(params: URLSearchParams): PolicyFilterState {
  return {
    statuses: params.getAll('status'),
    search: params.get('q') ?? '',
  }
}

export function serializePolicyFilters(filters: PolicyFilterState): URLSearchParams {
  const params = new URLSearchParams()
  for (const status of filters.statuses) params.append('status', status)
  if (filters.search) params.set('q', filters.search)
  return params
}

export function hasActivePolicyFilters(filters: PolicyFilterState): boolean {
  return filters.statuses.length > 0 || filters.search !== ''
}

export function togglePolicyStatus(
  filters: PolicyFilterState,
  status: string,
): PolicyFilterState {
  return {
    ...filters,
    statuses: filters.statuses.includes(status)
      ? filters.statuses.filter((value) => value !== status)
      : [...filters.statuses, status],
  }
}

/** Total across the knowledge base, whatever the active filter hides. */
export function totalFromStatusCounts(counts: Record<string, number>): number {
  return Object.values(counts).reduce((sum, count) => sum + count, 0)
}

export function summarizePolicyFilters(input: {
  shown: number
  total: number
  filters: PolicyFilterState
}): string {
  return hasActivePolicyFilters(input.filters)
    ? `Showing ${input.shown} of ${countLabel(input.total, 'item')}`
    : `Showing all ${countLabel(input.total, 'item')}`
}
