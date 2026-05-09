import { Outlet } from 'react-router-dom'

import { useDomainConfig } from '../../api/config'
import { useUiStore } from '../../stores/uiStore'
import { AiAssistantPanel } from './AiAssistantPanel'
import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'
import './layout.css'

export function AppShell() {
  const domainConfigQuery = useDomainConfig()
  const aiPanelOpen = useUiStore((state) => state.aiPanelOpen)

  return (
    <div className="app-shell">
      <Sidebar domainConfig={domainConfigQuery.data} />
      <div className="app-shell__workspace">
        <TopBar
          domainConfig={domainConfigQuery.data}
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