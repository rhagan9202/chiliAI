// Fixed locale so a count reads the same for every analyst on a shared queue,
// and so the rendered string does not depend on the host's ICU defaults.
const GROUPED = new Intl.NumberFormat('en-US')

/** `12,345 alerts` / `1 alert` — a count and its noun, agreeing in number. */
export function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${GROUPED.format(count)} ${count === 1 ? singular : plural}`
}
