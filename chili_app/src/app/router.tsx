import { createBrowserRouter, Navigate } from 'react-router-dom'
import type { ReactElement } from 'react'

import { AuthGuard } from '../components/AuthGuard'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import { AppShell } from '../components/layout/AppShell'
import { DomainConfigProvider } from '../contexts/DomainConfigContext'
import { AlertFeedPage } from '../pages/AlertFeedPage'
import { CaseManagementPage } from '../pages/CaseManagementPage'
import { ConfigurationPage } from '../pages/ConfigurationPage'
import { DashboardPage } from '../pages/DashboardPage'
import { InvestigationWorkbenchPage } from '../pages/InvestigationWorkbenchPage'
import { KnowledgeBaseManagerPage } from '../pages/KnowledgeBaseManagerPage'
import { Login } from '../pages/Login'
import { PagePlaceholder } from '../pages/PagePlaceholder'
import { PolicyIntelligencePage } from '../pages/PolicyIntelligencePage'
import { RagChatPage } from '../pages/RagChatPage'

function withPageBoundary(element: ReactElement) {
  return <ErrorBoundary>{element}</ErrorBoundary>
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (
      <AuthGuard>
        <DomainConfigProvider>
          <AppShell />
        </DomainConfigProvider>
      </AuthGuard>
    ),
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: 'dashboard', element: withPageBoundary(<DashboardPage />) },
      { path: 'alerts', element: withPageBoundary(<AlertFeedPage />) },
      { path: 'investigation', element: withPageBoundary(<InvestigationWorkbenchPage />) },
      { path: 'investigation/:entityId', element: withPageBoundary(<InvestigationWorkbenchPage />) },
      { path: 'cases', element: withPageBoundary(<CaseManagementPage />) },
      { path: 'knowledge-bases', element: withPageBoundary(<KnowledgeBaseManagerPage />) },
      { path: 'policy', element: withPageBoundary(<PolicyIntelligencePage />) },
      { path: 'rag-chat', element: withPageBoundary(<RagChatPage />) },
      { path: 'configuration', element: withPageBoundary(<ConfigurationPage />) },
      // Catch-all inside the authenticated shell — renders a placeholder for
      // any domain-configured page id that doesn't yet have a built component.
      // Lets a new domain pack ship a page id and route without a frontend
      // code change; devs can replace the placeholder when ready.
      {
        path: '*',
        element: (
          <PagePlaceholder title="Coming soon" eyebrow="Page not yet implemented">
            <p>
              This page is registered in the active domain config but the frontend
              component has not been wired yet.
            </p>
          </PagePlaceholder>
        ),
      },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
