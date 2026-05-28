import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useDomainConfig } from '../../api/config'
import { useDomainFeatures } from '../../api/config'
import { useRealtimeWorkspaceStream } from '../../api/realtime'
import { getDefaultRole, getLandingRoute, isRouteAllowed } from '../../app/access'
import { useUiStore } from '../../stores/uiStore'
import { AiAssistantPanel } from './AiAssistantPanel'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import './layout.css'

export function AppShell() {
  const domainConfigQuery = useDomainConfig()
  const domainFeaturesQuery = useDomainFeatures()
  const aiPanelOpen = useUiStore((state) => state.aiPanelOpen)
  const selectedRole = useUiStore((state) => state.selectedRole)
  const setAccessNotice = useUiStore((state) => state.setAccessNotice)
  const setSelectedRole = useUiStore((state) => state.setSelectedRole)
  const location = useLocation()

  useRealtimeWorkspaceStream()

  // Synchronously compute the effective role so route-access checks in this
  // render already use the default role once features are available — avoids
  // a one-render window where selectedRole is still null after queries resolve
  // but before the initialisation effect fires (which caused a spurious
  // "cannot access" banner on every hard reload).
  const effectiveRole =
    selectedRole ??
    (domainFeaturesQuery.data ? getDefaultRole(domainFeaturesQuery.data) : null)

  useEffect(() => {
    if (!domainFeaturesQuery.data) {
      return
    }

    const defaultRole = getDefaultRole(domainFeaturesQuery.data)
    if (!selectedRole || (selectedRole && !domainFeaturesQuery.data.roles[selectedRole])) {
      setSelectedRole(defaultRole)
    }
  }, [domainFeaturesQuery.data, selectedRole, setSelectedRole])

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
  const domainQueriesDone = !domainConfigQuery.isLoading && !domainFeaturesQuery.isLoading
  const routeBlocked = domainQueriesDone && !routeAllowed

  useEffect(() => {
    if (routeBlocked) {
      setAccessNotice('Selected role cannot access that page.')
    } else {
      // Clear the notice once the block resolves so it doesn't persist across
      // navigations or after the role is initialised.
      setAccessNotice(null)
    }
  }, [routeBlocked, setAccessNotice])

  if (routeBlocked) {
    return <Navigate replace to={landingRoute} />
  }

  return (
    <div className={aiPanelOpen ? 'app-shell' : 'app-shell app-shell--ai-closed'}>
      <Sidebar domainConfig={domainConfigQuery.data} domainFeatures={domainFeaturesQuery.data} selectedRole={selectedRole} />
      <div className="app-shell__workspace">
        <TopBar
          domainConfig={domainConfigQuery.data}
          domainFeatures={domainFeaturesQuery.data}
          loading={domainConfigQuery.isLoading}
          unavailable={domainConfigQuery.isError}
        />
        <main className="app-shell__main" aria-label="chiliAI workspace">
          <Outlet />
        </main>
      </div>
      {aiPanelOpen ? <AiAssistantPanel /> : null}
    </div>
  )
}
