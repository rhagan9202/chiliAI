import { useEffect, useMemo } from 'react'

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
  const setActiveConversation = useChatStore((s) => s.setActiveConversation)
  const conversation = useChatStore(
    (s) => s.conversations[conversationId],
  )
  const messages = useMemo(
    () => conversation?.messages ?? [],
    [conversation],
  )

  const { send, isStreaming, lastError } = useChatMessages()

  useEffect(() => {
    setActiveConversation(conversationId)
  }, [conversationId, setActiveConversation])

  const submit = (content: string): void => {
    void send({ conversationId, content })
  }

  return (
    <div className={styles.container} data-testid="chat-container">
      <div className={styles.header}>
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

      <div className={styles.body}>
        <MessageList messages={messages} />
        <MessageInput
          disabled={isStreaming}
          onSubmit={submit}
        />
      </div>
    </div>
  )
}
