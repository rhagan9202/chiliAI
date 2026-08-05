import { PanelRightOpen } from 'lucide-react'
import type { ReactNode } from 'react'

import { getDefaultRole } from '../../app/access'
import type { DomainConfig, DomainFeatures } from '../../api/contracts'
import { useUiStore } from '../../stores/uiStore'

type TopBarProps = {
  domainConfig?: DomainConfig
  domainFeatures?: DomainFeatures
  loading: boolean
  pageTitleOverride?: string
  unavailable: boolean
  workspaceControl?: ReactNode
}

export function TopBar({
  domainConfig,
  domainFeatures,
  loading,
  pageTitleOverride,
  unavailable,
  workspaceControl,
}: TopBarProps) {
  const toggleAiPanel = useUiStore((state) => state.toggleAiPanel)
  const selectedRole = useUiStore((state) => state.selectedRole)
  const setSelectedRole = useUiStore((state) => state.setSelectedRole)
  const realtimeConnected = useUiStore((state) => state.realtimeConnected)
  const title = pageTitleOverride ?? domainConfig?.domain.display_name ?? 'chiliAI Platform'
  const status = loading ? 'Loading config' : unavailable ? 'Config unavailable' : realtimeConnected ? 'Live updates' : 'Realtime reconnecting'
  const roleOptions = Object.keys(domainFeatures?.roles ?? {})
  const activeRole = selectedRole ?? getDefaultRole(domainFeatures) ?? roleOptions[0] ?? ''

  return (
    <header className="app-topbar">
      <div>
        {/* Not a heading: this is constant chrome. Screen-reader users
            navigating by heading were told every one of the 11 routes was
            called "Medicare Fraud Detection" (UXA-205). The page owns its h1
            via SectionHeader. */}
        <div className="app-topbar__title">{title}</div>
      </div>
      <div className="app-topbar__actions">
        {workspaceControl}
        {roleOptions.length > 0 ? (
          <label className="app-topbar__select-wrap">
            <span className="app-topbar__search-label">Active role</span>
            <select
              className="app-topbar__select"
              onChange={(event) => setSelectedRole(event.target.value)}
              value={activeRole}
            >
              {roleOptions.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <span className="app-topbar__badge">{status}</span>
        <button className="app-topbar__button" type="button" onClick={toggleAiPanel}>
          <PanelRightOpen size={16} />
          AI Panel
        </button>
      </div>
    </header>
  )
}
