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

import { getAllowedPageIds } from '../../app/access'
import type { DomainConfig, DomainFeatures } from '../../api/contracts'

type NavItem = {
  id: string
  label: string
  to: string
  icon: ComponentType<{ size?: number }>
  capability?: keyof DomainConfig['capabilities']
}

const navItems: NavItem[] = [
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
  const navItemsById = new Map(navItems.map((item) => [item.id, item]))
  const configuredItems: NavItem[] = domainConfig?.ui?.navigation?.pages.reduce<NavItem[]>(
    (items, page) => {
      const fallback = navItemsById.get(page.id)
      if (!fallback) {
        return items
      }

      items.push({
        ...fallback,
        capability:
          (page.capability as keyof DomainConfig['capabilities'] | undefined) ??
          fallback.capability,
        label: page.label,
        to: page.route,
      })
      return items
    },
    [],
  ) ?? []

  const navigationItems = configuredItems.length > 0 ? configuredItems : navItems
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