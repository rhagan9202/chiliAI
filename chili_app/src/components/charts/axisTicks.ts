/** Most ticks a count axis should draw before it reads as clutter. */
const MAX_TICKS = 6

/**
 * Integer tick values for a count axis, from 0 to at least `maxValue`.
 *
 * Recharts' automatic ticks divide the domain evenly, which produces fractional
 * gridlines on small integer data — a single critical alert rendered a Severity
 * Mix axis labelled 0.25 / 0.5 / 0.75, i.e. quarters of an alert (UXA-203).
 * Counts are discrete, so the axis has to be too.
 */
export function integerTicks(maxValue: number): number[] {
  const max =
    Number.isFinite(maxValue) && maxValue > 0 ? Math.ceil(maxValue) : 0

  // An all-zero (or empty) series still needs a scale to draw against.
  if (max === 0) return [0, 1]

  // Small counts: enumerate every value so no bar sits between gridlines.
  if (max < MAX_TICKS) {
    return Array.from({ length: max + 1 }, (_, index) => index)
  }

  // Larger ranges: step by a whole number, rounded up so the top tick covers
  // the data and every intermediate tick stays an integer.
  const step = Math.ceil(max / (MAX_TICKS - 1))
  const ticks: number[] = []
  for (let value = 0; value <= max; value += step) {
    ticks.push(value)
  }
  if (ticks[ticks.length - 1] < max) {
    ticks.push(ticks[ticks.length - 1] + step)
  }
  return ticks
}
