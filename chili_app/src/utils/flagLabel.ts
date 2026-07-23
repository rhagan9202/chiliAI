/**
 * Uppercased, dot-joined triage flag label for an alert row — e.g.
 * "BILLING · PEER-DEVIATION". Falls back to the severity word when the
 * alert carries no tags. Never invents a domain-specific string: the label
 * is built only from data already on the alert. Shared by the alert feed
 * triage rows and the dashboard lead card.
 */
export function flagLabelFor(alert: { tags: string[]; severity: string }): string {
  if (alert.tags.length > 0) {
    return alert.tags.map((tag) => tag.toUpperCase()).join(' · ')
  }
  return alert.severity.toUpperCase()
}
