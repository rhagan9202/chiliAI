import { Route, Routes } from 'react-router-dom'

import { KbDetailView } from './components/knowledgebase/KbDetailView'
import { AppShell } from './components/layout/AppShell'
import { AlertFeed } from './pages/AlertFeed'
import { ConfigEditor } from './pages/ConfigEditor'
import { Dashboard } from './pages/Dashboard'
import { InvestigationWorkbench } from './pages/InvestigationWorkbench'
import { KnowledgeBaseManager } from './pages/KnowledgeBaseManager'
import { NotFound } from './pages/NotFound'
import { RagChat } from './pages/RagChat'
import './App.css'

function App(): React.ReactElement {
  return (
    <Routes>
      <Route element={<AppShell />}>
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
  )
}

export default App
