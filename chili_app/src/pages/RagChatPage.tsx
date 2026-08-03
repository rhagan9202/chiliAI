import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { useDomainConfig } from '../api/config'
import {
  isStartConversationPartialError,
  useAddMessage,
  useConversation,
  useConversations,
  useCreateConversation,
  useStartConversationWithMessage,
} from '../api/rag'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import { EmptyKnowledgeBaseNotice } from '../components/knowledgebase/EmptyKnowledgeBaseNotice'
import { useActiveKnowledgeBase } from '../hooks/useActiveKnowledgeBase'
import { resolveRagCitationTarget } from '../lib/citationTargets'
import { buildRagMessageFilters, parseRagLaunchContext } from '../lib/ragContext'
import { countLabel } from '../utils/countLabel'
import { knowledgeBaseOptionLabel } from '../utils/knowledgeBaseStatus'
import { relativeAge } from '../utils/relativeTime'
import { starterPrompts } from '../utils/starterPrompts'
import './pages.css'

const contextTitleBySource = {
  alert: 'Alert investigation',
  case: 'Case investigation',
  entity: 'Entity investigation',
  housing: 'Housing investigation',
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
  const [searchParams] = useSearchParams()
  const launchContext = useMemo(() => parseRagLaunchContext(searchParams), [searchParams])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const launchQuestion = launchContext.question ?? ''
  const [draftState, setDraftState] = useState(() => ({
    launchQuestion,
    value: launchQuestion,
  }))
  const [retryFilters, setRetryFilters] = useState<Record<string, string | number | boolean> | null>(null)
  const [showContextualRetryMessage, setShowContextualRetryMessage] = useState(false)
  const {
    activeKnowledgeBaseId,
    knowledgeBases,
    isLoading: knowledgeBasesLoading,
    isError: knowledgeBasesError,
    setActiveKnowledgeBase,
  } = useActiveKnowledgeBase()
  const requestedKbId = launchContext.knowledgeBaseId
  const hasContextualLaunch =
    launchContext.source != null ||
    launchContext.alertId != null ||
    launchContext.entityId != null ||
    launchContext.caseId != null ||
    launchContext.evidencePackId != null ||
    launchContext.installationId != null ||
    launchContext.scorecardRunId != null ||
    launchContext.question != null
  // A contextual launch that names an unknown knowledge base must NOT silently
  // fall back to the workspace default — answering against a different corpus
  // than the alert/case the analyst arrived from would be worse than refusing.
  const selectedKnowledgeBaseId = knowledgeBases.some((kb) => kb.id === requestedKbId)
    ? requestedKbId
    : hasContextualLaunch
      ? null
      : activeKnowledgeBaseId
  const conversationQuery = useConversation(conversationId, selectedKnowledgeBaseId)
  const conversationsQuery = useConversations(selectedKnowledgeBaseId)
  const domainConfigQuery = useDomainConfig()
  const createConversationMutation = useCreateConversation()
  const startContextualThreadMutation = useStartConversationWithMessage()
  const addMessageMutation = useAddMessage(conversationId, selectedKnowledgeBaseId)
  const draft = draftState.launchQuestion === launchQuestion ? draftState.value : launchQuestion
  const setDraftForLaunchQuestion = (value: string) => setDraftState({ launchQuestion, value })
  const contextQuestion = launchQuestion.trim()
  const contextChips = [
    launchContext.source,
    launchContext.alertId,
    launchContext.entityId,
    launchContext.caseId,
    launchContext.evidencePackId,
    launchContext.installationId,
    launchContext.scorecardRunId,
  ].filter((value): value is string => typeof value === 'string' && value.length > 0)
  const canStartContextualThread = !conversationId && contextQuestion.length > 0

  if (knowledgeBasesLoading || (conversationId && conversationQuery.isLoading)) {
    return <LoadingState label="Loading RAG conversation" />
  }

  if (knowledgeBasesError) {
    return <ErrorState description="Your knowledge bases could not be loaded. Try again in a moment." />
  }

  if (conversationId && conversationQuery.isError) {
    return <ErrorState description="Your conversation history could not be loaded. Try again in a moment." />
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
            description="The assistant answers from an ingested knowledge base. Create one, ingest something into it, then come back and ask."
            title="No knowledge base available"
          />
        </Card>
      </section>
    )
  }

  const conversation = conversationQuery.data ?? null
  const conversations = conversationsQuery.data?.items ?? []
  const prompts = starterPrompts(domainConfigQuery.data ?? null)

  return (
    <section className="chat-page">
      <div className="chat-page__toolbar">
        <div>
          <div className="chat-page__eyebrow">Conversational RAG</div>
          {/* The page's own toolbar stands in for SectionHeader here, so this
              is the route's h1 (UXA-205: one h1 per page). */}
          <h1 className="chat-page__title">RAG Chat</h1>
        </div>
        <div className="chat-page__toolbar-controls">
          <Chip label={conversation?.title ?? 'No active conversation'} tone="info" />
          <select
            aria-label="Knowledge base"
            className="page-input--inline"
            id="rag-kb-select"
            onChange={(event) => {
              setActiveKnowledgeBase(event.target.value)
              setConversationId(null)
              setDraftForLaunchQuestion('')
              setRetryFilters(null)
              setShowContextualRetryMessage(false)
            }}
            value={selectedKnowledgeBaseId}
          >
            {knowledgeBases.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {knowledgeBaseOptionLabel(kb, knowledgeBases)}
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
                  title: `Investigation conversation ${new Date().toLocaleTimeString()}`,
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
            New conversation
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
              Start with this context
            </button>
          ) : null}
        </div>
      </div>

      <EmptyKnowledgeBaseNotice
        knowledgeBase={
          knowledgeBases.find((kb) => kb.id === selectedKnowledgeBaseId) ?? null
        }
      />

      {contextChips.length > 0 ? (
        <div className="alert-row-card__meta" aria-label="Launch context">
          {contextChips.map((chip) => (
            <Chip key={chip} label={chip} tone="default" />
          ))}
        </div>
      ) : null}

      {showContextualRetryMessage ? (
        <div className="alert-row-card__meta" role="status">
          The conversation was created, but the first message failed. Review it and send again.
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
                      const target = resolveRagCitationTarget({ citation, context: launchContext })
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
                          {target.kind === 'unsupported' ? (
                            <span className="metric-row__label">{target.reason}</span>
                          ) : null}
                        </>
                      )

                      return (
                        <li className="chat-citation" key={citationKey(message.id, citation, citationIndex)}>
                          {target.kind === 'link' ? (
                            <Link
                              aria-label={citationAccessibleName(citation)}
                              to={target.to}
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
          <div className="chat-page__starters">
            <EmptyState
              description="Ask a question below, or pick one of these to begin."
              title="No active conversation"
            />
            {/* Derived from the active pack, so the openers follow the domain
                rather than hardcoding fraud wording (UXA-403). */}
            {prompts.length > 0 ? (
              <div aria-label="Starter prompts" className="chat-page__starter-list" role="group">
                {prompts.map((prompt) => (
                  <button
                    className="page-button page-button--sm page-button--secondary"
                    key={prompt}
                    onClick={() => setDraftForLaunchQuestion(prompt)}
                    type="button"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </div>

      {conversations.length > 0 ? (
        <div className="chat-page__conversations">
          <span className="filter-group__label">Conversations</span>
          <ul aria-label="Conversations" className="chat-page__conversation-list">
            {conversations.map((item) => (
              <li key={item.id}>
                <button
                  className={
                    item.id === conversationId
                      ? 'page-list-item page-list-item--active'
                      : 'page-list-item'
                  }
                  onClick={() => setConversationId(item.id)}
                  type="button"
                >
                  <strong>{item.title}</strong>
                  <span className="metric-row__label">
                    {item.last_message ?? 'No messages yet'}
                  </span>
                  <span className="alert-row-card__age">
                    {countLabel(item.message_count, 'message')} · {relativeAge(item.updated_at)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

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
