import { Link } from 'react-router'

import type { RouteBlockReason } from '../../app/access'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'
import { SectionHeader } from '../ui/SectionHeader'

export interface RouteNotAvailableProps {
  /** The role the workspace is currently acting as, if one is resolved. */
  role: string | null
  /** Whether the pack or the role is what refused this route. */
  reason: RouteBlockReason | null
  /** Where the user can go instead. */
  landingRoute: string
  landingLabel: string
}

/**
 * Shown when the active pack or role may not open the current route.
 *
 * Deliberately rendered in place rather than redirecting: bouncing the user to
 * another page with no explanation leaves them unable to tell whether the page
 * is missing, broken, or simply not theirs — and it silently discards the URL
 * they asked for (UXA-102).
 *
 * The copy distinguishes pack-level exclusion (no role in this domain can open
 * it) from role-level exclusion (the pack enables it, this role doesn't), so
 * the analyst is not told to switch roles when switching roles cannot help.
 */
export function RouteNotAvailable({
  role,
  reason,
  landingRoute,
  landingLabel,
}: RouteNotAvailableProps): React.ReactElement {
  const subtitle =
    reason === 'pack'
      ? 'The active domain pack does not enable this page. Switch to a pack that includes it, or ask an administrator to edit the pack.'
      : role
        ? `The ${role} role does not include this page. Switch roles from the top bar, or ask an administrator to grant access.`
        : 'This page is not part of the active workspace configuration.'
  const description =
    reason === 'pack'
      ? 'This page is not part of the current domain pack. No role in this pack can open it; changing role will not help.'
      : role
        ? `You are working as ${role}. Pages outside that role's access are hidden from navigation; this one was reached directly by URL.`
        : 'Choose an available page to continue.'
  return (
    <section className="page-grid">
      <SectionHeader eyebrow="Access" subtitle={subtitle} title="Page not available" />
      <Card>
        <EmptyState
          action={
            <Link className="page-button" to={landingRoute}>
              Go to {landingLabel}
            </Link>
          }
          description={description}
          title={reason === 'pack' ? 'Not part of this pack' : 'Not available for your role'}
        />
      </Card>
    </section>
  )
}
