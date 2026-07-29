import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router'

import { useDomainConfig } from '../../api/config'
import { useDomainFeatures } from '../../api/config'
import { useRealtimeWorkspaceStream } from '../../api/realtime'
import { getLandingRoute, getRouteBlockReason, resolveRole } from '../../app/access'
import { readStoredRole, useUiStore } from '../../stores/uiStore'
import { ToastContainer } from '../common/Toast'
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
  // RAG Chat *is* the assistant; its own composer is the one to use there.
  const railSuppressed = location.pathname.startsWith('/rag-chat')

  useRealtimeWorkspaceStream()

  // Synchronously compute the effective role so route-access checks in this
  // render already use the default role once features are available — avoids
  // a one-render window where selectedRole is still null after queries resolve
  // but before the initialisation effect fires (which caused a spurious
  // "cannot access" banner on every hard reload).
  // A role remembered from a previous session outranks the pack default:
  // falling back to `default_role` on reload silently demotes the user and then
  // bounces them off whatever page that role cannot open (UXA-102). It only
  // outranks it while this pack still defines the role — `resolveRole` drops a
  // role left behind by a pack switch, which would otherwise collapse role
  // gating to pack level and leave the role control naming a role that is gone.
  const storedRole = readStoredRole()
  const effectiveRole = resolveRole(domainFeaturesQuery.data, selectedRole ?? storedRole)

  useEffect(() => {
    if (!domainFeaturesQuery.data) {
      return
    }
    // Persist the resolved role, so a stale value is actually replaced rather
    // than written back unchanged.
    if (selectedRole !== effectiveRole) {
      setSelectedRole(effectiveRole)
    }
  }, [domainFeaturesQuery.data, selectedRole, effectiveRole, setSelectedRole])

  const routeBlockReason = getRouteBlockReason(
    domainConfigQuery.data,
    domainFeaturesQuery.data,
    effectiveRole,
    location.pathname,
  )
  const routeAllowed = routeBlockReason === null
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
  // Only dress the top bar for a page we are actually rendering. On a refused
  // route the body already says "not available"; announcing another domain's
  // title above it would re-introduce the leak this gate closes (UXA-103).
  const pageTitleOverride =
    !routeBlocked && location.pathname.startsWith('/housing')
      ? 'Department of the Air Force Housing'
      : undefined

  return (
    <div className={aiPanelOpen && !railSuppressed ? 'app-shell' : 'app-shell app-shell--ai-closed'}>
      {/* The gate below reads `effectiveRole`; the nav must be built from the
          same role or it briefly offers links that are then refused. */}
      <Sidebar domainConfig={domainConfigQuery.data} domainFeatures={domainFeaturesQuery.data} selectedRole={effectiveRole} />
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
              reason={routeBlockReason}
              role={effectiveRole}
            />
          ) : (
            <Outlet />
          )}
        </main>
      </div>
      {/* Toasts render inside the router: a toast can carry a link to what it
          just created (UXA-405), and <Link> needs the router context. */}
      <ToastContainer />
      {/* One assistant, two surfaces (UXA-407): RAG Chat is the durable
          conversation, the rail is a quick ask that hands off to it. On RAG
          Chat itself the rail would be a second composer for the same job. */}
      {aiPanelOpen && !railSuppressed ? <AiAssistantPanel /> : null}
    </div>
  )
}
