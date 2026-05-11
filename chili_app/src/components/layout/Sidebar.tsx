import {
  Bot,
  BriefcaseBusiness,
  Circle,
  ClipboardList,
  Database,
  FileCog,
  Gauge,
  GitBranch,
  LayoutDashboard,
  ShieldCheck,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { NavLink } from 'react-router-dom'

import { getAllowedPageIds } from '../../app/access'
import type { DomainConfig, DomainFeatures } from '../../api/contracts'

type NavItem = {
  id: string
  label: string
  to: string
  icon: ComponentType<{ size?: number }>
  capability?: keyof DomainConfig['capabilities']
}

// Default icon registry by page id. Page ids not in this map fall back to a
// generic icon so a new domain config can ship pages without a code change.
const DEFAULT_ICONS: Record<string, ComponentType<{ size?: number }>> = {
  dashboard: LayoutDashboard,
  alerts: ClipboardList,
  investigation: GitBranch,
  cases: BriefcaseBusiness,
  knowledge_bases: Database,
  policy: ShieldCheck,
  rag_chat: Bot,
  configuration: FileCog,
}

// Default routes by page id, used only if domain config is unavailable.
const DEFAULT_NAV: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard },
  { id: 'alerts', label: 'Alert Feed', to: '/alerts', icon: ClipboardList },
  { id: 'investigation', label: 'Investigation', to: '/investigation', icon: GitBranch, capability: 'gnn' },
  { id: 'cases', label: 'Cases', to: '/cases', icon: BriefcaseBusiness },
  { id: 'knowledge_bases', label: 'Knowledge Bases', to: '/knowledge-bases', icon: Database },
  { id: 'policy', label: 'Policy Intelligence', to: '/policy', icon: ShieldCheck, capability: 'explainability' },
  { id: 'rag_chat', label: 'RAG Chat', to: '/rag-chat', icon: Bot, capability: 'rag_chat' },
  { id: 'configuration', label: 'Configuration', to: '/configuration', icon: FileCog },
]

type SidebarProps = {
  domainConfig?: DomainConfig
  domainFeatures?: DomainFeatures
  selectedRole: string | null
}

export function Sidebar({ domainConfig, domainFeatures, selectedRole }: SidebarProps) {
  const configuredItems: NavItem[] =
    domainConfig?.ui?.navigation?.pages.map((page) => ({
      id: page.id,
      label: page.label,
      to: page.route,
      icon: DEFAULT_ICONS[page.id] ?? Circle,
      capability: page.capability as keyof DomainConfig['capabilities'] | undefined,
    })) ?? []

  const navigationItems = configuredItems.length > 0 ? configuredItems : DEFAULT_NAV
  const allowedPageIds = new Set(getAllowedPageIds(domainFeatures, selectedRole))
  const visibleItems = navigationItems.filter((item) => {
    if (allowedPageIds.size > 0 && !allowedPageIds.has(item.id)) {
      return false
    }
    if (!item.capability || !domainConfig) {
      return true
    }
    return domainConfig.capabilities[item.capability]
  })

  return (
    <aside className="app-sidebar" aria-label="Primary navigation">
      <div className="app-sidebar__brand">
        <div className="app-sidebar__mark" aria-hidden="true">
          <Gauge size={18} />
        </div>
        <div>
          <div className="app-sidebar__title">chiliAI</div>
          <div className="app-sidebar__subtitle">Graph RAG Workbench</div>
        </div>
      </div>
      <nav className="app-sidebar__nav">
        {visibleItems.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              className={({ isActive }) =>
                isActive ? 'app-sidebar__link app-sidebar__link--active' : 'app-sidebar__link'
              }
              key={item.to}
              to={item.to}
            >
              <Icon size={16} />
              <span>{item.label}</span>
            </NavLink>
          )
        })}
      </nav>
    </aside>
  )
}
