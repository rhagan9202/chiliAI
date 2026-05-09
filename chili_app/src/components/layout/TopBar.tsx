import { PanelRightOpen, Search } from 'lucide-react'

import type { DomainConfig } from '../../api/contracts'
import { useUiStore } from '../../stores/uiStore'

type TopBarProps = {
  domainConfig?: DomainConfig
  loading: boolean
  unavailable: boolean
}

export function TopBar({ domainConfig, loading, unavailable }: TopBarProps) {
  const toggleAiPanel = useUiStore((state) => state.toggleAiPanel)
  const title = domainConfig?.domain.display_name ?? 'chiliAI Platform'
  const status = loading ? 'Loading config' : unavailable ? 'Config unavailable' : 'Development'

  return (
    <header className="app-topbar">
      <div>
        <div className="app-topbar__eyebrow">Production UI foundation</div>
        <h1 className="app-topbar__title">{title}</h1>
      </div>
      <div className="app-topbar__actions">
        <label className="app-topbar__search">
          <Search size={14} />
          <span className="app-topbar__search-label">Global search</span>
          <input placeholder="Entity, case, or document ID" type="search" />
        </label>
        <span className="app-topbar__badge">{status}</span>
        <button className="app-topbar__button" type="button" onClick={toggleAiPanel}>
          <PanelRightOpen size={16} />
          AI Panel
        </button>
      </div>
    </header>
  )
}