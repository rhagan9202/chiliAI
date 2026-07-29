import { type FormEvent, useMemo, useState } from 'react'
import { Bot, SendHorizontal } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'

import { useAlert } from '../../api/alerts'
import { useCase } from '../../api/cases'
import { useDomainConfig } from '../../api/config'
import { useInvestigationEntity } from '../../api/investigation'
import { buildRagChatUrl, parseRagLaunchContext, type RagLaunchContext } from '../../lib/ragContext'
import { getEntityTitle } from '../../utils/domainDisplay'

type AssistantContext = RagLaunchContext & {
  summary: string
}

/**
 * What the panel says while it has only an id. The id itself never appears in
 * the copy — "Alert context: ede44288-b501-4bb8-a50b-ef142bc12be7" told an
 * analyst nothing about what they were asking about (UXA-304). It stays
 * reachable as the element's `title`.
 */
const contextSummary = (context: RagLaunchContext): string | null => {
  if (context.source === 'alert' && context.alertId) {
    return 'Attached to the selected alert'
  }

  if (context.source === 'case' && context.caseId) {
    return 'Attached to the selected case'
  }

  if (context.source === 'entity' && context.entityId) {
    return 'Attached to the selected entity'
  }

  return null
}

/** The id behind the current context, kept for hover but out of the copy. */
const contextIdentifier = (context: RagLaunchContext): string | null => {
  if (context.source === 'alert') return context.alertId ?? null
  if (context.source === 'case') return context.caseId ?? null
  if (context.source === 'entity') return context.entityId ?? null
  return null
}

const parseAssistantContext = (pathname: string, search: string): AssistantContext | null => {
  const params = new URLSearchParams(search)
  const knowledgeBaseId = params.get('kb') || null

  if (pathname === '/alerts') {
    const alertId = params.get('alert') || null
    if (alertId) {
      return {
        knowledgeBaseId,
        source: 'alert',
        alertId,
        summary: 'Attached to the selected alert',
      }
    }
  }

  if (pathname === '/cases') {
    const caseId = params.get('case') || null
    if (caseId) {
      return { knowledgeBaseId, source: 'case', caseId, summary: 'Attached to the selected case' }
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

    return {
      knowledgeBaseId,
      source: 'entity',
      entityId,
      summary: 'Attached to the selected entity',
    }
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

  // These reads hit the same query keys the page behind the panel already
  // populated, so attaching a name costs a cache lookup, not a request.
  const domainConfigQuery = useDomainConfig()
  const alertQuery = useAlert(
    context?.source === 'alert' ? context.alertId ?? null : null,
    context?.knowledgeBaseId ?? null,
  )
  const caseQuery = useCase(
    context?.knowledgeBaseId ?? null,
    context?.source === 'case' ? context.caseId ?? null : null,
  )
  const entityQuery = useInvestigationEntity(
    context?.knowledgeBaseId ?? null,
    context?.source === 'entity' ? context.entityId ?? null : null,
  )

  const resolvedName = ((): string | null => {
    if (context?.source === 'alert' && alertQuery.data) {
      const { alert } = alertQuery.data
      return [alert.title, alert.entity_label].filter(Boolean).join(' · ') || null
    }
    if (context?.source === 'case' && caseQuery.data) {
      return caseQuery.data.case.title || null
    }
    if (context?.source === 'entity' && entityQuery.data && domainConfigQuery.data) {
      return getEntityTitle(entityQuery.data.entity, domainConfigQuery.data)
    }
    return null
  })()

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
          <div className="ai-panel__subtitle">Quick ask — opens in RAG Chat</div>
        </div>
      </div>
      <div className="ai-panel__body">
        <p title={context ? contextIdentifier(context) ?? undefined : undefined}>
          {context
            ? resolvedName ?? context.summary
            : 'Open an alert, case, or entity to ask about it here.'}
        </p>
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
