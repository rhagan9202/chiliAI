import { countLabel } from './countLabel'

/**
 * The triage filter model (UXA-401).
 *
 * The Alert Feed shipped a single-select chip row that conflated two
 * dimensions — All/Critical/High were severity, Acknowledged was status — so
 * "critical AND unacknowledged", the product's most common triage filter,
 * could not be expressed at all. Dimensions are independent here: selections
 * within one are OR, across dimensions are AND.
 *
 * State lives in the URL so a view is shareable and survives a reload.
 */

/**
 * The fields the model filters and sorts on. Structural rather than the full
 * `AlertListItem` so the pure model does not depend on optionality choices in
 * the generated wire DTO.
 */
export interface FilterableAlert {
  severity: string
  status: string
  entity_label: string
  title: string
  confidence: number
  created_at: string
}

export type AlertSortId = 'newest' | 'oldest' | 'severity' | 'confidence'

export interface AlertFilterState {
  severities: string[]
  statuses: string[]
  search: string
  sort: AlertSortId
  /** Inclusive `YYYY-MM-DD` bounds on `created_at`; empty means unbounded. */
  from: string
  to: string
}

export const ALERT_SORTS: readonly { id: AlertSortId; label: string }[] = [
  { id: 'newest', label: 'Newest first' },
  { id: 'oldest', label: 'Oldest first' },
  { id: 'severity', label: 'Severity' },
  { id: 'confidence', label: 'Confidence' },
]

/** Newest first: a triage queue is worked from the top, and age is its key. */
const DEFAULT_SORT: AlertSortId = 'newest'

export const EMPTY_ALERT_FILTERS: AlertFilterState = {
  severities: [],
  statuses: [],
  search: '',
  sort: DEFAULT_SORT,
  from: '',
  to: '',
}

const SEVERITY_RANK: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
}

function createdAt(alert: FilterableAlert): number {
  const parsed = Date.parse(alert.created_at)
  return Number.isNaN(parsed) ? 0 : parsed
}

/** Number of items per distinct key, so each filter option can show its count. */
export function countBy<T>(items: readonly T[], key: (item: T) => string): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const item of items) {
    const value = key(item)
    counts[value] = (counts[value] ?? 0) + 1
  }
  return counts
}

function withinDateRange(alert: FilterableAlert, from: string, to: string): boolean {
  if (!from && !to) return true
  // Compare on the ISO date prefix: the bounds are calendar days, and the
  // upper bound is inclusive of the whole day the analyst picked.
  const day = alert.created_at.slice(0, 10)
  if (from && day < from) return false
  if (to && day > to) return false
  return true
}

function matchesSearch(alert: FilterableAlert, search: string): boolean {
  if (!search) return true
  const needle = search.toLowerCase()
  return (
    alert.entity_label.toLowerCase().includes(needle) ||
    alert.title.toLowerCase().includes(needle)
  )
}

const COMPARATORS: Record<
  AlertSortId,
  (left: FilterableAlert, right: FilterableAlert) => number
> = {
  newest: (left, right) => createdAt(right) - createdAt(left),
  oldest: (left, right) => createdAt(left) - createdAt(right),
  // Ties break on recency so the order is total and stable.
  severity: (left, right) =>
    (SEVERITY_RANK[right.severity] ?? 0) - (SEVERITY_RANK[left.severity] ?? 0) ||
    createdAt(right) - createdAt(left),
  confidence: (left, right) =>
    right.confidence - left.confidence || createdAt(right) - createdAt(left),
}

export function applyAlertFilters<T extends FilterableAlert>(
  alerts: readonly T[],
  filters: AlertFilterState,
): T[] {
  const severities = new Set(filters.severities)
  const statuses = new Set(filters.statuses)
  const matched = alerts.filter(
    (alert) =>
      (severities.size === 0 || severities.has(alert.severity)) &&
      (statuses.size === 0 || statuses.has(alert.status)) &&
      matchesSearch(alert, filters.search) &&
      withinDateRange(alert, filters.from, filters.to),
  )
  return [...matched].sort(COMPARATORS[filters.sort] ?? COMPARATORS[DEFAULT_SORT])
}

function isSortId(value: string): value is AlertSortId {
  return ALERT_SORTS.some((option) => option.id === value)
}

/** Reads only the parameters this model owns, so `?kb=` and `?alert=` survive. */
export function parseAlertFilters(params: URLSearchParams): AlertFilterState {
  const sort = params.get('sort') ?? ''
  return {
    severities: params.getAll('severity'),
    statuses: params.getAll('status'),
    search: params.get('q') ?? '',
    sort: isSortId(sort) ? sort : DEFAULT_SORT,
    from: params.get('from') ?? '',
    to: params.get('to') ?? '',
  }
}

/** Writes only what differs from the default, so an unfiltered URL stays clean. */
export function serializeAlertFilters(filters: AlertFilterState): URLSearchParams {
  const params = new URLSearchParams()
  for (const severity of filters.severities) params.append('severity', severity)
  for (const status of filters.statuses) params.append('status', status)
  if (filters.search) params.set('q', filters.search)
  if (filters.sort !== DEFAULT_SORT) params.set('sort', filters.sort)
  if (filters.from) params.set('from', filters.from)
  if (filters.to) params.set('to', filters.to)
  return params
}

export function hasActiveAlertFilters(filters: AlertFilterState): boolean {
  return (
    filters.severities.length > 0 ||
    filters.statuses.length > 0 ||
    filters.search !== '' ||
    filters.from !== '' ||
    filters.to !== ''
  )
}

/** The result line: what is on screen, out of what exists. */
export function summarizeAlertFilters(input: {
  shown: number
  total: number
  filters: AlertFilterState
}): string {
  return hasActiveAlertFilters(input.filters)
    ? `Showing ${input.shown} of ${countLabel(input.total, 'alert')}`
    : `Showing all ${countLabel(input.total, 'alert')}`
}
