import { Link } from 'react-router'

import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'
import { SectionHeader } from '../ui/SectionHeader'

export interface RouteNotAvailableProps {
  /** The role the workspace is currently acting as, if one is resolved. */
  role: string | null
  /** Where the user can go instead. */
  landingRoute: string
  landingLabel: string
}

/**
 * Shown when the active role may not open the current route.
 *
 * Deliberately rendered in place rather than redirecting: bouncing the user to
 * another page with no explanation leaves them unable to tell whether the page
 * is missing, broken, or simply not theirs — and it silently discards the URL
 * they asked for (UXA-102).
 */
export function RouteNotAvailable({
  role,
  landingRoute,
  landingLabel,
}: RouteNotAvailableProps): React.ReactElement {
  return (
    <section className="page-grid">
      <SectionHeader
        eyebrow="Access"
        subtitle={
          role
            ? `The ${role} role does not include this page. Switch roles from the top bar, or ask an administrator to grant access.`
            : 'This page is not part of the active workspace configuration.'
        }
        title="Page not available"
      />
      <Card>
        <EmptyState
          action={
            <Link className="page-button" to={landingRoute}>
              Go to {landingLabel}
            </Link>
          }
          description={
            role
              ? `You are working as ${role}. Pages outside that role's access are hidden from navigation; this one was reached directly by URL.`
              : 'Choose an available page to continue.'
          }
          title="Not available for your role"
        />
      </Card>
    </section>
  )
}
