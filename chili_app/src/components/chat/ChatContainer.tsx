import { useEffect, useMemo, useState } from 'react'

import { useKnowledgeBases } from '../../hooks/useKnowledgeBases'
import { useChatMessages } from '../../hooks/useChatMessages'
import { useChatStore } from '../../stores/chatStore'
import { MessageInput } from './MessageInput'
import { MessageList } from './MessageList'
import styles from './ChatContainer.module.css'

export interface ChatContainerProps {
  conversationId: string
}

export function ChatContainer({
  conversationId,
}: ChatContainerProps): React.ReactElement {
  const kbQuery = useKnowledgeBases()
  const setActiveConversation = useChatStore((s) => s.setActiveConversation)
  const conversation = useChatStore(
    (s) => s.conversations[conversationId],
  )
  const messages = useMemo(
    () => conversation?.messages ?? [],
    [conversation],
  )
  const [selectedKb, setSelectedKb] = useState<string>('')

  const { send, isStreaming, lastError } = useChatMessages()

  useEffect(() => {
    setActiveConversation(conversationId)
  }, [conversationId, setActiveConversation])

  const knowledgeBases = useMemo(
    () => kbQuery.data?.items ?? [],
    [kbQuery.data],
  )

  const effectiveKb =
    selectedKb !== ''
      ? selectedKb
      : knowledgeBases.length > 0
        ? knowledgeBases[0].id
        : ''

  const submit = (content: string): void => {
    if (effectiveKb === '') return
    void send({ conversationId, kbId: effectiveKb, content })
  }

  return (
    <div className={styles.container} data-testid="chat-container">
      <div className={styles.header}>
        <label className={styles.kbSelector}>
          <span>Knowledge base</span>
          <select
            value={effectiveKb}
            onChange={(event) => setSelectedKb(event.target.value)}
            disabled={kbQuery.isLoading || knowledgeBases.length === 0}
            data-testid="kb-selector"
          >
            {kbQuery.isLoading ? (
              <option value="">Loading…</option>
            ) : knowledgeBases.length === 0 ? (
              <option value="">No knowledge bases available</option>
            ) : (
              knowledgeBases.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}
                </option>
              ))
            )}
          </select>
        </label>
        {isStreaming ? (
          <span className={styles.indicator} aria-live="polite">
            <span className={styles.dot} aria-hidden="true" />
            <span className={styles.dot} aria-hidden="true" />
            <span className={styles.dot} aria-hidden="true" />
            <span>streaming…</span>
          </span>
        ) : null}
      </div>

      {lastError ? (
        <div className={styles.errorText} role="alert">
          {lastError.message}
        </div>
      ) : null}
      {kbQuery.error ? (
        <div className={styles.errorText} role="alert">
          Could not load knowledge bases: {kbQuery.error.message}
        </div>
      ) : null}

      <div className={styles.body}>
        <MessageList messages={messages} />
        <MessageInput
          disabled={isStreaming || effectiveKb === ''}
          onSubmit={submit}
        />
      </div>
    </div>
  )
}
