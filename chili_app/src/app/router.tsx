import { createBrowserRouter, Navigate } from 'react-router'
import type { ReactElement } from 'react'

import { AuthGuard } from '../components/AuthGuard'
import { ErrorBoundary } from '../components/common/ErrorBoundary'
import { AppShell } from '../components/layout/AppShell'
import { LandingRedirect } from '../components/layout/LandingRedirect'
import { AlertFeedPage } from '../pages/AlertFeedPage'
import { CaseManagementPage } from '../pages/CaseManagementPage'
import { ConfigurationPage } from '../pages/ConfigurationPage'
import { DashboardPage } from '../pages/DashboardPage'
import { GovernancePage } from '../pages/GovernancePage'
import { HousingExecutivePage } from '../pages/HousingExecutivePage'
import { InvestigationWorkbenchPage } from '../pages/InvestigationWorkbenchPage'
import { KnowledgeBaseManagerPage } from '../pages/KnowledgeBaseManagerPage'
import { Login } from '../pages/Login'
import { NotFoundPage } from '../pages/NotFoundPage'
import { PolicyIntelligencePage } from '../pages/PolicyIntelligencePage'
import { RagChatPage } from '../pages/RagChatPage'
import { ScorecardRunPage } from '../pages/ScorecardRunPage'

function withPageBoundary(element: ReactElement) {
  return <ErrorBoundary>{element}</ErrorBoundary>
}

export const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    path: '/',
    element: (
      <AuthGuard>
        <AppShell />
      </AuthGuard>
    ),
    children: [
      { index: true, element: <LandingRedirect /> },
      { path: 'dashboard', element: withPageBoundary(<DashboardPage />) },
      { path: 'housing', element: withPageBoundary(<HousingExecutivePage />) },
      { path: 'scorecards/:runId', element: withPageBoundary(<ScorecardRunPage />) },
      { path: 'alerts', element: withPageBoundary(<AlertFeedPage />) },
      { path: 'investigation', element: withPageBoundary(<InvestigationWorkbenchPage />) },
      { path: 'investigation/:entityId', element: withPageBoundary(<InvestigationWorkbenchPage />) },
      { path: 'cases', element: withPageBoundary(<CaseManagementPage />) },
      { path: 'knowledge-bases', element: withPageBoundary(<KnowledgeBaseManagerPage />) },
      { path: 'knowledgebases', element: <Navigate to="/knowledge-bases" replace /> },
      { path: 'policy', element: withPageBoundary(<PolicyIntelligencePage />) },
      { path: 'governance', element: withPageBoundary(<GovernancePage />) },
      { path: 'rag-chat', element: withPageBoundary(<RagChatPage />) },
      { path: 'configuration', element: withPageBoundary(<ConfigurationPage />) },
      // Catch-all inside the authenticated shell. It covers both a domain pack
      // that ships a page id the SPA hasn't built yet and — far more often — a
      // mistyped address; NotFoundPage picks the right explanation from the
      // configured routes and always offers a way back.
      { path: '*', element: withPageBoundary(<NotFoundPage />) },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
])
