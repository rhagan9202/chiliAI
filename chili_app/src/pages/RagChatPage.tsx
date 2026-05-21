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
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={conversation?.title ?? 'No active thread'} tone="info" />}
        eyebrow="Conversational RAG"
        subtitle="Conversation creation and message submission now exercise the backend chat endpoints and seeded RAG service."
        title="RAG Chat"
      />

      <Card>
        <div className="metric-stack">
          <div className="metric-row">
            <label className="metric-row__label" htmlFor="rag-kb-select">
              Knowledge base
            </label>
            <select
              className="page-input"
              id="rag-kb-select"
              onChange={(event) => {
                // setSearchParams (not navigate) because RAG Chat has no entity sub-path to reset.
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
          </div>
        </div>
      </Card>

      <div className="page-actions-inline">
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
                onSuccess: (conversation) => {
                  setConversationId(conversation.id)
                },
              },
            )
          }
          type="button"
        >
          Start new thread
        </button>
      </div>

      <Card>
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
                {message.citation_ids.length > 0 ? (
                  <div className="alert-row-card__meta">
                    {message.citation_ids.map((citationId) => (
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
      </Card>

      <Card>
        <div className="metric-stack">
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
            Send message
          </button>
        </div>
      </Card>
    </section>
  )
}
