/**
 * Time metrics for the Queue Health tab (UXA-402).
 *
 * The tab showed counts and status words but nothing about *time*, which is
 * what "health" means for a work queue: how long the oldest untouched item has
 * been waiting, how quickly things get looked at, and whether the team is
 * keeping up with arrivals.
 */

export interface QueueAlert {
  status: string
  created_at: string
  /** Last write to the row; for an acknowledged alert, when that happened. */
  updated_at: string
}

export interface QueueHealth {
  openCount: number
  /** How long the oldest undispositioned alert has waited, or null. */
  oldestOpenAge: string | null
  /** Median, not mean — one stale outlier must not move the typical figure. */
  medianTimeToAcknowledge: string | null
  dispositionedLastDay: number
}

/** Statuses that mean nobody has dealt with the alert yet. */
const WAITING_STATUSES = new Set(['open', 'investigating'])

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

const MONTH_DAY = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
})

function parse(timestamp: string): number | null {
  const value = Date.parse(timestamp)
  return Number.isNaN(value) ? null : value
}

/**
 * `20 min`, `3 hrs`, `2 days` — a duration, not a point in time.
 *
 * Spelled out rather than `20m`/`2d`: these render inside chips that
 * uppercase, and "11M" reads as eleven months.
 */
function formatDuration(milliseconds: number): string {
  if (milliseconds < HOUR) return `${Math.max(1, Math.round(milliseconds / MINUTE))} min`
  if (milliseconds < DAY) {
    const hours = Math.round(milliseconds / HOUR)
    return `${hours} ${hours === 1 ? 'hr' : 'hrs'}`
  }
  const days = Math.round(milliseconds / DAY)
  return `${days} ${days === 1 ? 'day' : 'days'}`
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0
    ? ((sorted[middle - 1] ?? 0) + (sorted[middle] ?? 0)) / 2
    : (sorted[middle] ?? 0)
}

export function queueHealth(
  alerts: readonly QueueAlert[],
  now: Date = new Date(),
): QueueHealth {
  const waiting = alerts.filter((alert) => WAITING_STATUSES.has(alert.status))
  const oldestCreated = waiting
    .map((alert) => parse(alert.created_at))
    .filter((value): value is number => value !== null)
    .sort((left, right) => left - right)[0]

  const acknowledgementTimes = alerts
    .filter((alert) => alert.status === 'acknowledged')
    .map((alert) => {
      const created = parse(alert.created_at)
      const updated = parse(alert.updated_at)
      return created === null || updated === null ? null : Math.max(0, updated - created)
    })
    .filter((value): value is number => value !== null)

  const dayAgo = now.getTime() - DAY
  const dispositionedLastDay = alerts.filter((alert) => {
    if (WAITING_STATUSES.has(alert.status)) return false
    const updated = parse(alert.updated_at)
    return updated !== null && updated >= dayAgo
  }).length

  const medianMilliseconds = median(acknowledgementTimes)
  return {
    openCount: waiting.length,
    oldestOpenAge:
      oldestCreated === undefined
        ? null
        : formatDuration(Math.max(0, now.getTime() - oldestCreated)),
    medianTimeToAcknowledge:
      medianMilliseconds === null ? null : formatDuration(medianMilliseconds),
    dispositionedLastDay,
  }
}

/**
 * Alerts raised per day across the trailing window, one bucket per day so the
 * axis is never sparse.
 */
export function backlogTrend(
  alerts: readonly QueueAlert[],
  now: Date = new Date(),
  days = 30,
): { label: string; value: number }[] {
  const buckets = new Map<string, number>()
  for (let offset = days - 1; offset >= 0; offset -= 1) {
    const day = new Date(now.getTime() - offset * DAY)
    buckets.set(day.toISOString().slice(0, 10), 0)
  }
  for (const alert of alerts) {
    const day = alert.created_at.slice(0, 10)
    if (buckets.has(day)) buckets.set(day, (buckets.get(day) ?? 0) + 1)
  }
  return [...buckets.entries()].map(([day, value]) => ({
    label: MONTH_DAY.format(new Date(`${day}T00:00:00Z`)),
    value,
  }))
}
