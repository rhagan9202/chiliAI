/**
 * Alert age, for a queue that is sorted and triaged by it.
 *
 * Fixed locale and UTC: analysts working the same queue from different places
 * must read the same timestamp, and a relative age is only trustworthy if the
 * absolute one behind it is unambiguous.
 */
const ABSOLUTE_FORMAT = new Intl.DateTimeFormat('en-US', {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'UTC',
})

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR
const FORTNIGHT = 14 * DAY

/** `3h ago` — compact enough to sit beside the subject line. */
export function relativeAge(timestamp: string, now: Date = new Date()): string {
  const parsed = Date.parse(timestamp)
  if (Number.isNaN(parsed)) return ''

  // A clock-skewed future timestamp is not "in -2 minutes"; the sub-minute
  // branch absorbs it, since every negative elapsed is below MINUTE.
  const elapsed = now.getTime() - parsed
  if (elapsed < MINUTE) return 'just now'
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)}m ago`
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)}h ago`
  if (elapsed < FORTNIGHT) return `${Math.floor(elapsed / DAY)}d ago`
  return `${Math.floor(elapsed / (7 * DAY))}w ago`
}

/** The unambiguous timestamp behind the relative age, for a hover title. */
export function absoluteTime(timestamp: string): string {
  const parsed = Date.parse(timestamp)
  if (Number.isNaN(parsed)) return ''
  return `${ABSOLUTE_FORMAT.format(new Date(parsed))} UTC`
}
