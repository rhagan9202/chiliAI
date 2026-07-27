import { countLabel } from './countLabel'

/**
 * Bulk-triage selection state (UXA-406).
 *
 * Selection is a set of alert ids, held by the page rather than the rows, so
 * it can be summarized and acted on as a whole. Every operation returns a new
 * set — React state must not be mutated in place.
 */

export function toggleSelection(current: ReadonlySet<string>, alertId: string): Set<string> {
  const next = new Set(current)
  if (!next.delete(alertId)) next.add(alertId)
  return next
}

/**
 * Selects what is currently on screen. "All" means all *in the current
 * filter* — offering to act on rows the analyst cannot see would be a trap.
 */
export function selectAll(visibleAlertIds: readonly string[]): Set<string> {
  return new Set(visibleAlertIds)
}

/**
 * Drops anything a filter change took out of view, so a bulk action can never
 * touch an alert the analyst is no longer looking at.
 */
export function pruneSelection(
  current: ReadonlySet<string>,
  visibleAlertIds: readonly string[],
): Set<string> {
  const visible = new Set(visibleAlertIds)
  return new Set([...current].filter((alertId) => visible.has(alertId)))
}

export function clearSelection(): Set<string> {
  return new Set()
}

/** The persistent summary line, and the count a confirmation must state. */
export function describeSelection(count: number): string {
  return `${countLabel(count, 'alert')} selected`
}
