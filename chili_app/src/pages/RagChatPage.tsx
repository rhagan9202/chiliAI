import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useKnowledgeBases } from '../api/knowledgebases'
import { useAddMessage, useConversation, useCreateConversation } from '../api/rag'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { EmptyState } from '../components/ui/EmptyState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function RagChatPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const knowledgeBasesQuery = useKnowledgeBases()
  const knowledgeBases = knowledgeBasesQuery.data?.items ?? []
  const requestedKbId = searchParams.get('kb')
  const selectedKnowledgeBaseId = knowledgeBases.some((kb) => kb.id === requestedKbId)
    ? requestedKbId
    : knowledgeBases[0]?.id ?? null
  const conversationQuery = useConversation(conversationId)
  const createConversationMutation = useCreateConversation()
  const addMessageMutation = useAddMessage(conversationId)

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
              setDraft('')
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
                  },
                },
              )
            }
            type="button"
          >
            New thread
          </button>
        </div>
      </div>

      <div className="chat-page__thread">
        {conversation ? (
          <div className="chat-thread">
            {conversation.messages.map((message) => (
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
                    {(message.citations ?? []).map((citation) => (
                      <li className="chat-citation" key={`${message.id}-${citation.content_id}`}>
                        <div className="chat-citation__header">
                          <strong>{citation.document_id ?? citation.record_id}</strong>
                          <span className="chat-citation__score">
                            {(citation.score * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="chat-citation__snippet">{citation.snippet}</p>
                        <span className="metric-row__label">
                          {citation.content_id}
                          {citation.chunk_index != null ? ` · chunk ${citation.chunk_index}` : ''}
                        </span>
                      </li>
                    ))}
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
            onChange={(event) => setDraft(event.target.value)}
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
                filters: {},
              })
              setDraft('')
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
