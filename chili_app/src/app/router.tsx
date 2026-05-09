import { createBrowserRouter, Navigate } from 'react-router-dom'

import { AppShell } from '../components/layout/AppShell'
import { AlertFeedPage } from '../pages/AlertFeedPage'
import { CaseManagementPage } from '../pages/CaseManagementPage'
import { ConfigurationPage } from '../pages/ConfigurationPage'
import { DashboardPage } from '../pages/DashboardPage'
import { InvestigationWorkbenchPage } from '../pages/InvestigationWorkbenchPage'
import { KnowledgeBaseManagerPage } from '../pages/KnowledgeBaseManagerPage'
import { PolicyIntelligencePage } from '../pages/PolicyIntelligencePage'
import { RagChatPage } from '../pages/RagChatPage'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
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
    ],
  },
])