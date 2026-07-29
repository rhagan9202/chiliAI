import { Link, useLocation } from 'react-router'

import { useDomainConfig, useDomainFeatures } from '../api/config'
import { getLandingRoute, resolveRole } from '../app/access'
import { describeUnknownRoute } from '../app/unknownRoute'
import { readStoredRole, useUiStore } from '../stores/uiStore'
import { PagePlaceholder } from './PagePlaceholder'

/**
 * The authenticated catch-all. A domain pack may declare a page the SPA has not
 * built yet, but the far more common arrival is a mistyped or stale address —
 * so the copy is chosen from the route, and either way there is a way out.
 *
 * The way out is resolved from the active pack and role. A hardcoded
 * `/dashboard` is not a way out under a pack that declares no dashboard: it
 * turned a mistyped address into "Page not available", refusing the user twice
 * over.
 */
export function NotFoundPage() {
  const location = useLocation()
  const domainConfigQuery = useDomainConfig()
  const domainFeaturesQuery = useDomainFeatures()
  const selectedRole = useUiStore((state) => state.selectedRole)
  const storedRole = readStoredRole()
  const navigationPages = domainConfigQuery.data?.ui?.navigation?.pages ?? []
  const configuredRoutes = navigationPages.map((page) => page.route)
  const copy = describeUnknownRoute(location.pathname, configuredRoutes)

  const role = resolveRole(domainFeaturesQuery.data, selectedRole ?? storedRole)
  const landingRoute = getLandingRoute(domainConfigQuery.data, domainFeaturesQuery.data, role)
  const landingLabel =
    navigationPages.find((page) => page.route === landingRoute)?.label ?? 'the workspace'

  return (
    <PagePlaceholder eyebrow="Wrong turn" title={copy.title}>
      <p>{copy.description}</p>
      <p>
        <Link className="page-button" to={landingRoute}>
          Back to {landingLabel}
        </Link>
      </p>
    </PagePlaceholder>
  )
}
