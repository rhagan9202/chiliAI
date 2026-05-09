import { NavLink } from 'react-router-dom'

import styles from './Sidebar.module.css'

export interface SidebarProps {
  open: boolean
  onToggle: () => void
}

interface NavItem {
  to: string
  label: string
  icon: string
  end?: boolean
}

const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: 'Dashboard', icon: '◆', end: true },
  { to: '/knowledgebases', label: 'Knowledge Bases', icon: '⛁' },
  { to: '/alerts', label: 'Alerts', icon: '⚑' },
  { to: '/investigation', label: 'Investigation', icon: '◉' },
  { to: '/chat', label: 'RAG Chat', icon: '✦' },
  { to: '/config', label: 'Configuration', icon: '⚙' },
]

export function Sidebar({ open, onToggle }: SidebarProps): React.ReactElement {
  return (
    <>
      <button
        type="button"
        className={styles.mobileToggle}
        onClick={onToggle}
        aria-label={open ? 'Close navigation' : 'Open navigation'}
        aria-expanded={open}
      >
        ☰
      </button>
      <aside
        className={styles.sidebar}
        data-open={open}
        aria-label="Primary navigation"
      >
        <div className={styles.header}>
          <span className={styles.brand}>chiliAI</span>
          <button
            type="button"
            className={styles.toggle}
            onClick={onToggle}
            aria-label={open ? 'Collapse sidebar' : 'Expand sidebar'}
            aria-expanded={open}
          >
            {open ? '«' : '»'}
          </button>
        </div>
        <nav className={styles.nav}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                isActive ? `${styles.link} ${styles.linkActive}` : styles.link
              }
            >
              <span className={styles.icon} aria-hidden="true">
                {item.icon}
              </span>
              <span className={styles.label}>{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  )
}
