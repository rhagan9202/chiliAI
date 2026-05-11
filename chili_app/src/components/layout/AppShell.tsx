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
  const setSelectedRole = useUiStore((state) => state.setSelectedRole)
  const location = useLocation()

  useRealtimeWorkspaceStream()

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
    selectedRole,
    location.pathname,
  )
  const landingRoute = getLandingRoute(
    domainConfigQuery.data,
    domainFeaturesQuery.data,
    selectedRole,
  )

  if (!domainConfigQuery.isLoading && !domainFeaturesQuery.isLoading && !routeAllowed) {
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
