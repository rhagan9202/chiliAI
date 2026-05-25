import { PanelRightOpen } from 'lucide-react'

import { getDefaultRole } from '../../app/access'
import type { DomainConfig, DomainFeatures } from '../../api/contracts'
import { useUiStore } from '../../stores/uiStore'

type TopBarProps = {
  domainConfig?: DomainConfig
  domainFeatures?: DomainFeatures
  loading: boolean
  unavailable: boolean
}

export function TopBar({ domainConfig, domainFeatures, loading, unavailable }: TopBarProps) {
  const toggleAiPanel = useUiStore((state) => state.toggleAiPanel)
  const selectedRole = useUiStore((state) => state.selectedRole)
  const setSelectedRole = useUiStore((state) => state.setSelectedRole)
  const realtimeConnected = useUiStore((state) => state.realtimeConnected)
  const title = domainConfig?.domain.display_name ?? 'chiliAI Platform'
  const status = loading ? 'Loading config' : unavailable ? 'Config unavailable' : realtimeConnected ? 'Live updates' : 'Realtime reconnecting'
  const roleOptions = Object.keys(domainFeatures?.roles ?? {})
  const activeRole = selectedRole ?? getDefaultRole(domainFeatures) ?? roleOptions[0] ?? ''

  return (
    <header className="app-topbar">
      <div>
        <h1 className="app-topbar__title">{title}</h1>
      </div>
      <div className="app-topbar__actions">
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