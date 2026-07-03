import { Chip } from '../ui/Chip'
import { isDomainMismatch } from './domainMismatch'

type KbDomainBadgeProps = {
  /** `domain` stamped on the knowledge base at creation (null for legacy KBs). */
  kbDomain: string | null | undefined
  /** `domain.name` of the currently active domain configuration. */
  activeDomainName: string | null | undefined
}

/**
 * Warn-only domain provenance badge for knowledge base lists/cards.
 *
 * - Mismatch (KB stamped with a different domain than the active one): a
 *   warning chip. It never blocks or disables any action.
 * - Unknown (legacy KB with no stamped domain): a subtle, tolerated chip.
 * - Match: renders nothing.
 */
export function KbDomainBadge({ kbDomain, activeDomainName }: KbDomainBadgeProps) {
  if (!kbDomain) {
    return (
      <span
        data-testid="kb-domain-unknown"
        title="This knowledge base predates domain stamping; its creating domain is unknown."
      >
        <Chip label="domain unknown" tone="default" />
      </span>
    )
  }

  if (isDomainMismatch(kbDomain, activeDomainName)) {
    return (
      <span
        data-testid="kb-domain-mismatch"
        title={`Created under the "${kbDomain}" domain; the active domain is "${activeDomainName ?? 'unknown'}". Its content may not match the active domain's entity types. No action is blocked.`}
      >
        <Chip label={`Created under ${kbDomain}`} tone="warning" />
      </span>
    )
  }

  return null
}
