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
  tags?: readonly string[]
  assignee?: string | null
  case_state?: string | null
  score_freshness?: string | null
  evidence_pack_id?: string | null
}

export type AlertSortId = 'newest' | 'oldest' | 'severity' | 'confidence'

export interface AlertFilterState {
  severities: string[]
  statuses: string[]
  typologies: string[]
  assignees: string[]
  caseStates: string[]
  scoreFreshnesses: string[]
  evidenceAvailability: string[]
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
  typologies: [],
  assignees: [],
  caseStates: [],
  scoreFreshnesses: [],
  evidenceAvailability: [],
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

function normalizedAssignee(alert: FilterableAlert): string {
  return alert.assignee?.trim() || 'unassigned'
}

function normalizedCaseState(alert: FilterableAlert): string {
  return alert.case_state?.trim() || 'no_case'
}

function normalizedScoreFreshness(alert: FilterableAlert): string {
  return alert.score_freshness?.trim() || 'unknown'
}

function normalizedEvidenceAvailability(alert: FilterableAlert): string {
  return alert.evidence_pack_id ? 'with_evidence' : 'without_evidence'
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
  const typologies = new Set(filters.typologies)
  const assignees = new Set(filters.assignees)
  const caseStates = new Set(filters.caseStates)
  const scoreFreshnesses = new Set(filters.scoreFreshnesses)
  const evidenceAvailability = new Set(filters.evidenceAvailability)
  const matched = alerts.filter(
    (alert) =>
      (severities.size === 0 || severities.has(alert.severity)) &&
      (statuses.size === 0 || statuses.has(alert.status)) &&
      (typologies.size === 0 || (alert.tags ?? []).some((tag) => typologies.has(tag))) &&
      (assignees.size === 0 || assignees.has(normalizedAssignee(alert))) &&
      (caseStates.size === 0 || caseStates.has(normalizedCaseState(alert))) &&
      (scoreFreshnesses.size === 0 ||
        scoreFreshnesses.has(normalizedScoreFreshness(alert))) &&
      (evidenceAvailability.size === 0 ||
        evidenceAvailability.has(normalizedEvidenceAvailability(alert))) &&
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
    typologies: params.getAll('typology'),
    assignees: params.getAll('assignee'),
    caseStates: params.getAll('case'),
    scoreFreshnesses: params.getAll('freshness'),
    evidenceAvailability: params.getAll('evidence'),
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
  for (const typology of filters.typologies) params.append('typology', typology)
  for (const assignee of filters.assignees) params.append('assignee', assignee)
  for (const caseState of filters.caseStates) params.append('case', caseState)
  for (const freshness of filters.scoreFreshnesses) params.append('freshness', freshness)
  for (const availability of filters.evidenceAvailability) params.append('evidence', availability)
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
    filters.typologies.length > 0 ||
    filters.assignees.length > 0 ||
    filters.caseStates.length > 0 ||
    filters.scoreFreshnesses.length > 0 ||
    filters.evidenceAvailability.length > 0 ||
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
