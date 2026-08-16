import { NavLink } from 'react-router'

import { knowledgeBaseWorkspacePath, WORKSPACE_SECTIONS } from '../../utils/knowledgeBaseRoutes'
import type { WorkspaceSection } from '../../utils/knowledgeBaseRoutes'
import './kb.css'

const SECTION_LABELS: Record<WorkspaceSection, string> = {
  overview: 'Overview',
  add: 'Add data',
  data: 'Data',
  runs: 'Runs',
  settings: 'Settings',
}

type WorkspaceTabsProps = {
  knowledgeBaseId: string
}

/**
 * Section navigation as links, not buttons.
 *
 * Each section is a real address, so the tabs must be openable in a new tab,
 * copyable, and reachable by the browser's own back button — which a
 * `role="tablist"` of buttons is not.
 */
export function WorkspaceTabs({ knowledgeBaseId }: WorkspaceTabsProps) {
  return (
    <nav aria-label="Knowledge base sections" className="kb-workspace__tabs">
      {WORKSPACE_SECTIONS.map((section) => (
        <NavLink
          className={({ isActive }) =>
            isActive ? 'tabs__button tabs__button--active' : 'tabs__button'
          }
          end={section === 'overview'}
          key={section}
          to={knowledgeBaseWorkspacePath(knowledgeBaseId, section)}
        >
          {SECTION_LABELS[section]}
        </NavLink>
      ))}
    </nav>
  )
}
