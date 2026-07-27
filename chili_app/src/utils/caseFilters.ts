import { countLabel } from './countLabel'

/**
 * The case-queue filter model (UXA-401).
 *
 * Cases carried the same single-select chip row the Alert Feed had, so "open
 * or in review" — the working set an analyst actually wants — could not be
 * stated. Deliberately narrower than `alertFilters`: a case queue has no
 * severity, no confidence and no useful age sort at this size, and inventing
 * dimensions the data does not support would be worse than omitting them.
 */

export interface FilterableCase {
  title: string
  status: string
}

export interface CaseFilterState {
  statuses: string[]
  search: string
}

export const EMPTY_CASE_FILTERS: CaseFilterState = {
  statuses: [],
  search: '',
}

export function applyCaseFilters<T extends FilterableCase>(
  cases: readonly T[],
  filters: CaseFilterState,
): T[] {
  const statuses = new Set(filters.statuses)
  const needle = filters.search.toLowerCase()
  return cases.filter(
    (item) =>
      (statuses.size === 0 || statuses.has(item.status)) &&
      (needle === '' || item.title.toLowerCase().includes(needle)),
  )
}

/** Reads only the parameters this model owns, so `?kb=` and `?case=` survive. */
export function parseCaseFilters(params: URLSearchParams): CaseFilterState {
  return {
    statuses: params.getAll('status'),
    search: params.get('q') ?? '',
  }
}

export function serializeCaseFilters(filters: CaseFilterState): URLSearchParams {
  const params = new URLSearchParams()
  for (const status of filters.statuses) params.append('status', status)
  if (filters.search) params.set('q', filters.search)
  return params
}

export function hasActiveCaseFilters(filters: CaseFilterState): boolean {
  return filters.statuses.length > 0 || filters.search !== ''
}

export function summarizeCaseFilters(input: {
  shown: number
  total: number
  filters: CaseFilterState
}): string {
  return hasActiveCaseFilters(input.filters)
    ? `Showing ${input.shown} of ${countLabel(input.total, 'case')}`
    : `Showing all ${countLabel(input.total, 'case')}`
}
