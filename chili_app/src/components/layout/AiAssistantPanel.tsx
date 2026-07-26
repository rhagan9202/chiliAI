import { type FormEvent, useMemo, useState } from 'react'
import { Bot, SendHorizontal } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'

import { buildRagChatUrl, parseRagLaunchContext, type RagLaunchContext } from '../../lib/ragContext'

type AssistantContext = RagLaunchContext & {
  summary: string
}

const contextSummary = (context: RagLaunchContext): string | null => {
  if (context.source === 'alert' && context.alertId) {
    return `Alert context: ${context.alertId}`
  }

  if (context.source === 'case' && context.caseId) {
    return `Case context: ${context.caseId}`
  }

  if (context.source === 'entity' && context.entityId) {
    return `Entity context: ${context.entityId}`
  }

  return null
}

const parseAssistantContext = (pathname: string, search: string): AssistantContext | null => {
  const params = new URLSearchParams(search)
  const knowledgeBaseId = params.get('kb') || null

  if (pathname === '/alerts') {
    const alertId = params.get('alert') || null
    if (alertId) {
      return { knowledgeBaseId, source: 'alert', alertId, summary: `Alert context: ${alertId}` }
    }
  }

  if (pathname === '/cases') {
    const caseId = params.get('case') || null
    if (caseId) {
      return { knowledgeBaseId, source: 'case', caseId, summary: `Case context: ${caseId}` }
    }
  }

  const investigationMatch = pathname.match(/^\/investigation\/([^/]+)$/)
  if (investigationMatch) {
    let entityId: string
    try {
      entityId = decodeURIComponent(investigationMatch[1])
    } catch {
      return null
    }

    return { knowledgeBaseId, source: 'entity', entityId, summary: `Entity context: ${entityId}` }
  }

  if (pathname === '/rag-chat') {
    const context = parseRagLaunchContext(params)
    const summary = contextSummary(context)
    return summary ? { ...context, summary } : null
  }

  return null
}

export function AiAssistantPanel() {
  const location = useLocation()
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const context = useMemo(
    () => parseAssistantContext(location.pathname, location.search),
    [location.pathname, location.search],
  )
  const canSend = context != null && draft.trim().length > 0

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!context || !canSend) {
      return
    }

    navigate(buildRagChatUrl({ ...context, question: draft.trim() }))
  }

  return (
    <aside className="ai-panel" aria-label="AI investigator assistant">
      <div className="ai-panel__header">
        <div className="ai-panel__icon" aria-hidden="true">
          <Bot size={16} />
        </div>
        <div>
          <div className="ai-panel__title">AI Investigator</div>
          <div className="ai-panel__subtitle">Triage support, not a final decision</div>
        </div>
      </div>
      <div className="ai-panel__body">
        <p>{context ? context.summary : 'Open an alert, case, or entity to attach context.'}</p>
      </div>
      <form className="ai-panel__composer" onSubmit={handleSubmit}>
        <input
          aria-label="Ask the AI investigator"
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask about this workspace..."
          value={draft}
        />
        <button aria-label="Send message" disabled={!canSend} type="submit">
          <SendHorizontal size={15} />
        </button>
      </form>
    </aside>
  )
}
