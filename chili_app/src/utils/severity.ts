import type { ChipTone } from '../components/ui/chipTones'

/**
 * The single severity → colour mapping for the whole product.
 *
 * Before this existed, `critical` rendered red on the Alert Feed and amber on
 * the entity workbench (which hardcoded `warning` for every severity), and two
 * pages carried their own duplicate `toneForSeverity`. The same alert changed
 * colour depending on which screen you were looking at (UXA-205).
 */
const SEVERITY_TONES: Record<string, ChipTone> = {
  critical: 'danger',
  high: 'danger',
  medium: 'warning',
  low: 'info',
}

export function severityTone(severity: string): ChipTone {
  return SEVERITY_TONES[severity.toLowerCase()] ?? 'default'
}

/**
 * Tone for a count badge. Zero is never an alarm: "Failed workflows 0" in red
 * reads as a failure at a glance, which is the opposite of what it reports.
 */
export function countTone(count: number, tone: ChipTone): ChipTone {
  return count > 0 ? tone : 'default'
}
