import { Link, useLocation } from 'react-router'

import { useDomainConfig } from '../api/config'
import { describeUnknownRoute } from '../app/unknownRoute'
import { PagePlaceholder } from './PagePlaceholder'

/**
 * The authenticated catch-all. A domain pack may declare a page the SPA has not
 * built yet, but the far more common arrival is a mistyped or stale address —
 * so the copy is chosen from the route, and either way there is a way out.
 */
export function NotFoundPage() {
  const location = useLocation()
  const domainConfigQuery = useDomainConfig()
  const configuredRoutes =
    domainConfigQuery.data?.ui?.navigation?.pages.map((page) => page.route) ?? []
  const copy = describeUnknownRoute(location.pathname, configuredRoutes)

  return (
    <PagePlaceholder eyebrow="Wrong turn" title={copy.title}>
      <p>{copy.description}</p>
      <p>
        <Link className="page-button" to="/dashboard">
          Back to the Dashboard
        </Link>
      </p>
    </PagePlaceholder>
  )
}
