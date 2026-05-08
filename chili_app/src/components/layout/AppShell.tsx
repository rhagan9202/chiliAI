import { Outlet } from 'react-router-dom'

import { useSession } from '../../contexts/SessionContext'
import { useAppStore } from '../../stores/appStore'
import { ErrorBoundary } from '../common/ErrorBoundary'
import { Sidebar } from './Sidebar'

export function AppShell(): React.ReactElement {
  const sidebarOpen = useAppStore((state) => state.sidebarOpen)
  const toggleSidebar = useAppStore((state) => state.toggleSidebar)
  const { user, signOut } = useSession()

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onToggle={toggleSidebar} />
      <main className="app-main">
        <header className="app-header">
          <div className="app-header-spacer" />
          {user !== null && (
            <div className="app-header-user">
              <span className="app-header-email">{user.email ?? user.user_id}</span>
              <button type="button" onClick={() => void signOut()}>
                Sign out
              </button>
            </div>
          )}
        </header>
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
