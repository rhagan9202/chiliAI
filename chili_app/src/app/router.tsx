import { createBrowserRouter, Navigate } from 'react-router-dom'

import { AuthGuard } from '../components/AuthGuard'
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
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'alerts', element: <AlertFeedPage /> },
      { path: 'investigation', element: <InvestigationWorkbenchPage /> },
      { path: 'investigation/:entityId', element: <InvestigationWorkbenchPage /> },
      { path: 'cases', element: <CaseManagementPage /> },
      { path: 'knowledge-bases', element: <KnowledgeBaseManagerPage /> },
      { path: 'policy', element: <PolicyIntelligencePage /> },
      { path: 'rag-chat', element: <RagChatPage /> },
      { path: 'configuration', element: <ConfigurationPage /> },
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
