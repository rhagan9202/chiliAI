import { Route, Routes } from 'react-router-dom'

import { AuthGuard } from './components/AuthGuard'
import { KbDetailView } from './components/knowledgebase/KbDetailView'
import { AppShell } from './components/layout/AppShell'
import { SessionProvider } from './contexts/SessionContext'
import { AlertFeed } from './pages/AlertFeed'
import { ConfigEditor } from './pages/ConfigEditor'
import { Dashboard } from './pages/Dashboard'
import { InvestigationWorkbench } from './pages/InvestigationWorkbench'
import { KnowledgeBaseManager } from './pages/KnowledgeBaseManager'
import { Login } from './pages/Login'
import { NotFound } from './pages/NotFound'
import { RagChat } from './pages/RagChat'
import './App.css'

function App(): React.ReactElement {
  return (
    <SessionProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <AuthGuard>
              <AppShell />
            </AuthGuard>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="knowledgebases" element={<KnowledgeBaseManager />} />
          <Route path="knowledgebases/:kbId" element={<KbDetailView />} />
          <Route path="alerts" element={<AlertFeed />} />
          <Route path="investigation" element={<InvestigationWorkbench />} />
          <Route path="chat" element={<RagChat />} />
          <Route path="config" element={<ConfigEditor />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </SessionProvider>
  )
}

export default App
