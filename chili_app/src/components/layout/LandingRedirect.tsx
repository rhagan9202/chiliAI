import { Navigate } from 'react-router'

import { useDomainConfig, useDomainFeatures } from '../../api/config'
import { getLandingRoute, resolveRole } from '../../app/access'
import { readStoredRole, useUiStore } from '../../stores/uiStore'
import { LoadingState } from '../ui/LoadingState'

/**
 * Sends "/" to the page the active pack and role actually land on.
 *
 * A fixed redirect to `/dashboard` broke every pack that does not declare a
 * dashboard page. The Air Force housing pack enables only housing, knowledge
 * bases, RAG chat and configuration, so the post-login redirect to "/" put
 * every sign-in on "Page not available" — the one screen a user should never
 * be greeted with.
 *
 * The pack has to resolve before anything is decided; redirecting to a guess
 * first is what produced the wrong landing page.
 */
export function LandingRedirect(): React.ReactElement {
  const domainConfigQuery = useDomainConfig()
  const domainFeaturesQuery = useDomainFeatures()
  const selectedRole = useUiStore((state) => state.selectedRole)
  const storedRole = readStoredRole()

  if (domainConfigQuery.isLoading || domainFeaturesQuery.isLoading) {
    return <LoadingState label="Opening your workspace" />
  }

  const role = resolveRole(domainFeaturesQuery.data, selectedRole ?? storedRole)

  return (
    <Navigate
      replace
      to={getLandingRoute(domainConfigQuery.data, domainFeaturesQuery.data, role)}
    />
  )
}
