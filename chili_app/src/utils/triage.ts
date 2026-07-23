/**
 * Severity → CSS color-variable mapping for the triage numeral treatment.
 * Critical/high map to red, medium to amber, everything else (low) to
 * green. Shared by the alert feed triage rows and the dashboard lead card.
 */
export function triageNumeralColor(severity: string): string {
  if (severity === 'critical' || severity === 'high') {
    return 'var(--c-red)'
  }
  if (severity === 'medium') {
    return 'var(--c-amber)'
  }
  return 'var(--c-green)'
}
