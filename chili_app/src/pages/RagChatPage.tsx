import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { useKnowledgeBases } from '../api/knowledgebases'
import {
  isStartConversationPartialError,
  useAddMessage,
  useConversation,
  useCreateConversation,
  useStartConversationWithMessage,
} from '../api/rag'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import {
  buildRagMessageFilters,
  citationNavigationTarget,
  parseRagLaunchContext,
} from '../lib/ragContext'
import './pages.css'

const contextTitleBySource = {
  alert: 'Alert investigation',
  case: 'Case investigation',
  entity: 'Entity investigation',
} as const

type ChatCitation = {
  record_id?: string | null
  content_id?: string | null
  document_id?: string | null
  chunk_index?: number | null
}

function citationDisplayId(citation: ChatCitation) {
  return citation.document_id ?? citation.record_id ?? 'citation'
}

function citationAccessibleName(citation: ChatCitation) {
  return [
    'Open citation context',
    citationDisplayId(citation),
    citation.content_id,
    citation.record_id,
    citation.chunk_index != null ? `chunk ${citation.chunk_index}` : null,
  ]
    .filter((value): value is string => typeof value === 'string' && value.length > 0)
    .join(' ')
}

function citationKey(messageId: string, citation: ChatCitation, index: number) {
  return [
    messageId,
    citation.content_id,
    citation.record_id,
    citation.document_id,
    citation.chunk_index ?? 'no-chunk',
    index,
  ]
    .filter((value): value is string | number => value != null)
    .join(':')
}

export function RagChatPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const launchContext = useMemo(() => parseRagLaunchContext(searchParams), [searchParams])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const launchQuestion = launchContext.question ?? ''
  const [draftState, setDraftState] = useState(() => ({
    launchQuestion,
    value: launchQuestion,
  }))
  const [retryFilters, setRetryFilters] = useState<Record<string, string | number | boolean> | null>(null)
  const [showContextualRetryMessage, setShowContextualRetryMessage] = useState(false)
  const knowledgeBasesQuery = useKnowledgeBases()
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const requestedKbId = launchContext.knowledgeBaseId
  const selectedKnowledgeBaseId = knowledgeBases.some((kb) => kb.id === requestedKbId)
    ? requestedKbId
    : knowledgeBases[0]?.id ?? null
  const conversationQuery = useConversation(conversationId)
  const createConversationMutation = useCreateConversation()
  const startContextualThreadMutation = useStartConversationWithMessage()
  const addMessageMutation = useAddMessage(conversationId)
  const draft = draftState.launchQuestion === launchQuestion ? draftState.value : launchQuestion
  const setDraftForLaunchQuestion = (value: string) => setDraftState({ launchQuestion, value })
  const contextQuestion = launchQuestion.trim()
  const contextChips = [
    launchContext.source,
    launchContext.alertId,
    launchContext.entityId,
    launchContext.caseId,
    launchContext.evidencePackId,
  ].filter((value): value is string => typeof value === 'string' && value.length > 0)
  const canStartContextualThread = !conversationId && contextQuestion.length > 0

  if (knowledgeBasesQuery.isLoading || (conversationId && conversationQuery.isLoading)) {
    return <LoadingState label="Loading RAG conversation" />
  }

  if (knowledgeBasesQuery.isError) {
    return <ErrorState description="Knowledge base inventory could not be loaded from the backend." />
  }

  if (conversationId && conversationQuery.isError) {
    return <ErrorState description="RAG conversation history could not be loaded from the backend." />
  }

  if (!selectedKnowledgeBaseId) {
    return (
      <section className="page-grid">
        <SectionHeader
          actions={<Chip label="No knowledge base" tone="default" />}
          eyebrow="Conversational RAG"
          subtitle="Create a knowledge base before starting an investigation chat."
          title="RAG Chat"
        />
        <Card>
          <EmptyState
            action={
              <button
                className="page-button"
                onClick={() => navigate('/knowledge-bases')}
                type="button"
              >
                + Create Knowledge Base
              </button>
            }
            description="RAG conversations need at least one knowledge base for retrieval context. Create one and return here to start a thread."
            title="No knowledge base available"
          />
        </Card>
      </section>
    )
  }

  const conversation = conversationQuery.data ?? null

  return (
    <section className="chat-page">
      <div className="chat-page__toolbar">
        <div>
          <div className="chat-page__eyebrow">Conversational RAG</div>
          <h2 className="chat-page__title">RAG Chat</h2>
        </div>
        <div className="chat-page__toolbar-controls">
          <Chip label={conversation?.title ?? 'No active thread'} tone="info" />
          <select
            aria-label="Knowledge base"
            className="page-input--inline"
            id="rag-kb-select"
            onChange={(event) => {
              const next = new URLSearchParams(searchParams)
              next.set('kb', event.target.value)
              setSearchParams(next)
              setConversationId(null)
              setDraftForLaunchQuestion('')
              setRetryFilters(null)
              setShowContextualRetryMessage(false)
            }}
            value={selectedKnowledgeBaseId}
          >
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name} · {kb.status}
              </option>
            ))}
          </select>
          <button
            className="page-button"
            disabled={createConversationMutation.isPending}
            onClick={() =>
              createConversationMutation.mutate(
                {
                  knowledge_base_id: selectedKnowledgeBaseId,
                  title: `Investigation thread ${new Date().toLocaleTimeString()}`,
                },
                {
                  onSuccess: (created) => {
                    setConversationId(created.id)
                    setRetryFilters(null)
                    setShowContextualRetryMessage(false)
                  },
                },
              )
            }
            type="button"
          >
            New thread
          </button>
          {canStartContextualThread ? (
            <button
              className="page-button"
              disabled={startContextualThreadMutation.isPending}
              onClick={() => {
                startContextualThreadMutation.mutate(
                  {
                    knowledge_base_id: selectedKnowledgeBaseId,
                    title:
                      launchContext.source != null
                        ? contextTitleBySource[launchContext.source]
                        : 'Entity investigation',
                    content: contextQuestion,
                    filters: buildRagMessageFilters(launchContext),
                  },
                  {
                    onError: (error) => {
                      if (isStartConversationPartialError(error)) {
                        setConversationId(error.createdConversation.id)
                        setRetryFilters(buildRagMessageFilters(launchContext))
                        setShowContextualRetryMessage(true)
                      }
                    },
                    onSuccess: (updated) => {
                      setConversationId(updated.id)
                      setDraftForLaunchQuestion('')
                      setRetryFilters(null)
                      setShowContextualRetryMessage(false)
                    },
                  },
                )
              }}
              type="button"
            >
              Start contextual thread
            </button>
          ) : null}
        </div>
      </div>

      {contextChips.length > 0 ? (
        <div className="alert-row-card__meta" aria-label="Launch context">
          {contextChips.map((chip) => (
            <Chip key={chip} label={chip} tone="default" />
          ))}
        </div>
      ) : null}

      {showContextualRetryMessage ? (
        <div className="alert-row-card__meta" role="status">
          Thread was created, but the first message failed. Review and send again.
        </div>
      ) : null}

      <div className="chat-page__thread">
        {conversation ? (
          <div className="chat-thread">
            {(conversation.messages ?? []).map((message) => (
              <div
                className={
                  message.role === 'assistant'
                    ? 'chat-bubble chat-bubble--assistant'
                    : 'chat-bubble'
                }
                key={message.id}
              >
                <strong>{message.role}</strong>
                <p>{message.content}</p>
                {(message.citations ?? []).length > 0 ? (
                  <ul className="chat-citations" aria-label="Citations">
                    {(message.citations ?? []).map((citation, citationIndex) => {
                      const target = citationNavigationTarget(citation, launchContext)
                      const citationContent = (
                        <>
                          <div className="chat-citation__header">
                            <strong>{citationDisplayId(citation)}</strong>
                            <span className="chat-citation__score">
                              {(citation.score * 100).toFixed(0)}%
                            </span>
                          </div>
                          <p className="chat-citation__snippet">{citation.snippet}</p>
                          <span className="metric-row__label">
                            {citation.content_id}
                            {citation.chunk_index != null ? ` · chunk ${citation.chunk_index}` : ''}
                          </span>
                        </>
                      )

                      return (
                        <li className="chat-citation" key={citationKey(message.id, citation, citationIndex)}>
                          {target ? (
                            <Link
                              aria-label={citationAccessibleName(citation)}
                              to={`${target.pathname}${target.search ? `?${target.search}` : ''}`}
                            >
                              {citationContent}
                            </Link>
                          ) : (
                            citationContent
                          )}
                        </li>
                      )
                    })}
                  </ul>
                ) : (message.citation_ids ?? []).length > 0 ? (
                  <div className="alert-row-card__meta">
                    {(message.citation_ids ?? []).map((citationId) => (
                      <Chip key={citationId} label={citationId} tone="default" />
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            description="Start a thread to ask questions against the current knowledge base."
            title="No active conversation"
          />
        )}
      </div>

      <div className="chat-page__compose">
        <div className="chat-page__compose-row">
          <textarea
            className="page-textarea"
            onChange={(event) => setDraftForLaunchQuestion(event.target.value)}
            placeholder="Ask the investigation assistant about an entity, alert, or evidence trail"
            value={draft}
          />
          <button
            className="page-button"
            disabled={!conversationId || draft.trim().length === 0 || addMessageMutation.isPending}
            onClick={() => {
              addMessageMutation.mutate({
                content: draft,
                include_graph_context: true,
              filters: retryFilters ?? {},
            })
              setDraftForLaunchQuestion('')
              setRetryFilters(null)
              setShowContextualRetryMessage(false)
            }}
            type="button"
          >
            Send
          </button>
        </div>
      </div>
    </section>
  )
}
