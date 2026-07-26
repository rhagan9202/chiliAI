import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router'

import { useDomainConfig } from '../../api/config'
import { useDomainFeatures } from '../../api/config'
import { useRealtimeWorkspaceStream } from '../../api/realtime'
import { getDefaultRole, getLandingRoute, isRouteAllowed } from '../../app/access'
import { readStoredRole, useUiStore } from '../../stores/uiStore'
import { AiAssistantPanel } from './AiAssistantPanel'
import { RouteNotAvailable } from './RouteNotAvailable'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import './layout.css'

export function AppShell() {
  const domainConfigQuery = useDomainConfig()
  const domainFeaturesQuery = useDomainFeatures()
  const aiPanelOpen = useUiStore((state) => state.aiPanelOpen)
  const selectedRole = useUiStore((state) => state.selectedRole)
  const setSelectedRole = useUiStore((state) => state.setSelectedRole)
  const location = useLocation()

  useRealtimeWorkspaceStream()

  // Synchronously compute the effective role so route-access checks in this
  // render already use the default role once features are available — avoids
  // a one-render window where selectedRole is still null after queries resolve
  // but before the initialisation effect fires (which caused a spurious
  // "cannot access" banner on every hard reload).
  // A role remembered from a previous session outranks the pack default:
  // falling back to `default_role` on reload silently demotes the user and then
  // bounces them off whatever page that role cannot open (UXA-102).
  const storedRole = readStoredRole()
  const effectiveRole =
    selectedRole ??
    (domainFeaturesQuery.data
      ? (storedRole !== null && domainFeaturesQuery.data.roles[storedRole]
          ? storedRole
          : getDefaultRole(domainFeaturesQuery.data))
      : null)

  useEffect(() => {
    if (!domainFeaturesQuery.data) {
      return
    }
    if (!selectedRole || !domainFeaturesQuery.data.roles[selectedRole]) {
      setSelectedRole(effectiveRole)
    }
  }, [domainFeaturesQuery.data, selectedRole, effectiveRole, setSelectedRole])

  const routeAllowed = isRouteAllowed(
    domainConfigQuery.data,
    domainFeaturesQuery.data,
    effectiveRole,
    location.pathname,
  )
  const landingRoute = getLandingRoute(
    domainConfigQuery.data,
    domainFeaturesQuery.data,
    effectiveRole,
  )
  const landingLabel =
    domainConfigQuery.data?.ui?.navigation?.pages.find((page) => page.route === landingRoute)
      ?.label ?? 'the workspace'
  const domainQueriesDone = !domainConfigQuery.isLoading && !domainFeaturesQuery.isLoading
  const routeBlocked = domainQueriesDone && !routeAllowed
  const pageTitleOverride = location.pathname.startsWith('/housing')
    ? 'Department of the Air Force Housing'
    : undefined

  return (
    <div className={aiPanelOpen ? 'app-shell' : 'app-shell app-shell--ai-closed'}>
      <Sidebar domainConfig={domainConfigQuery.data} domainFeatures={domainFeaturesQuery.data} selectedRole={selectedRole} />
      <div className="app-shell__workspace">
        <TopBar
          domainConfig={domainConfigQuery.data}
          domainFeatures={domainFeaturesQuery.data}
          loading={domainConfigQuery.isLoading}
          pageTitleOverride={pageTitleOverride}
          unavailable={domainConfigQuery.isError}
        />
        <main className="app-shell__main" aria-label="chiliAI workspace">
          {routeBlocked ? (
            <RouteNotAvailable
              landingLabel={landingLabel}
              landingRoute={landingRoute}
              role={effectiveRole}
            />
          ) : (
            <Outlet />
          )}
        </main>
      </div>
      {aiPanelOpen ? <AiAssistantPanel /> : null}
    </div>
  )
}
