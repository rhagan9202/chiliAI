import {
  Bot,
  BriefcaseBusiness,
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

import type { DomainConfig } from '../../api/contracts'

type NavItem = {
  label: string
  to: string
  icon: ComponentType<{ size?: number }>
  capability?: keyof DomainConfig['capabilities']
}

const navItems: NavItem[] = [
  { label: 'Dashboard', to: '/dashboard', icon: LayoutDashboard },
  { label: 'Alert Feed', to: '/alerts', icon: ClipboardList },
  { label: 'Investigation', to: '/investigation', icon: GitBranch, capability: 'gnn' },
  { label: 'Cases', to: '/cases', icon: BriefcaseBusiness },
  { label: 'Knowledge Bases', to: '/knowledge-bases', icon: Database },
  { label: 'Policy Intelligence', to: '/policy', icon: ShieldCheck, capability: 'rag_chat' },
  { label: 'RAG Chat', to: '/rag-chat', icon: Bot, capability: 'rag_chat' },
  { label: 'Configuration', to: '/configuration', icon: FileCog },
]

type SidebarProps = {
  domainConfig?: DomainConfig
}

export function Sidebar({ domainConfig }: SidebarProps) {
  const visibleItems = navItems.filter((item) => {
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