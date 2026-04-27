import { Outlet } from 'react-router-dom'

import { ErrorBoundary } from '../common/ErrorBoundary'
import { useAppStore } from '../../stores/appStore'
import { Sidebar } from './Sidebar'

export function AppShell(): React.ReactElement {
  const sidebarOpen = useAppStore((state) => state.sidebarOpen)
  const toggleSidebar = useAppStore((state) => state.toggleSidebar)

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onToggle={toggleSidebar} />
      <main className="app-main">
        <ErrorBoundary>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
