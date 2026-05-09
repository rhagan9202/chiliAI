import { useState } from 'react'

import { useAddMessage, useConversation, useCreateConversation } from '../api/rag'
import { Card } from '../components/ui/Card'
import { Chip } from '../components/ui/Chip'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingState } from '../components/ui/LoadingState'
import { SectionHeader } from '../components/ui/SectionHeader'
import './pages.css'

export function RagChatPage() {
  const [conversationId, setConversationId] = useState<string>('conversation-001')
  const [draft, setDraft] = useState('')
  const conversationQuery = useConversation(conversationId)
  const createConversationMutation = useCreateConversation()
  const addMessageMutation = useAddMessage(conversationId)

  if (conversationQuery.isLoading) {
    return <LoadingState label="Loading RAG conversation" />
  }

  if (conversationQuery.isError) {
    return <ErrorState description="RAG conversation history could not be loaded from the backend." />
  }

  if (!conversationQuery.data) {
    return <LoadingState label="Waiting for conversation data" />
  }

  return (
    <section className="page-grid">
      <SectionHeader
        actions={<Chip label={conversationQuery.data.title} tone="info" />}
        eyebrow="Conversational RAG"
        subtitle="Conversation creation and message submission now exercise the backend chat endpoints and seeded RAG service."
        title="RAG Chat"
      />

      <div className="page-actions-inline">
        <button
          className="page-button"
          onClick={() =>
            createConversationMutation.mutate(
              {
                knowledge_base_id: 'kb-1',
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
        <div className="chat-thread">
          {conversationQuery.data.messages.map((message) => (
            <div className={message.role === 'assistant' ? 'chat-bubble chat-bubble--assistant' : 'chat-bubble'} key={message.id}>
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
            disabled={draft.trim().length === 0 || addMessageMutation.isPending}
            onClick={() => {
              addMessageMutation.mutate({ content: draft, include_graph_context: true, filters: {} })
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