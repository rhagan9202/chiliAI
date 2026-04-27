import { useEffect, useRef } from 'react'

import type { ChatMessage } from '../../stores/chatStore'
import { CitationLink } from './CitationLink'
import styles from './ChatContainer.module.css'

export interface MessageListProps {
  messages: ChatMessage[]
}

export function MessageList({ messages }: MessageListProps): React.ReactElement {
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const node = bottomRef.current
    if (node && typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className={styles.messageList} data-testid="message-list">
        <p className={styles.empty}>
          Ask a question about the selected knowledge base to begin.
        </p>
      </div>
    )
  }

  return (
    <div className={styles.messageList} data-testid="message-list">
      {messages.map((message) => (
        <div
          key={message.id}
          className={`${styles.message} ${
            message.role === 'user' ? styles.user : styles.assistant
          }`}
          data-role={message.role}
          data-pending={message.pending ? 'true' : 'false'}
        >
          {message.content.length === 0 && message.pending ? (
            <span className={styles.indicator} aria-live="polite">
              <span className={styles.dot} aria-hidden="true" />
              <span className={styles.dot} aria-hidden="true" />
              <span className={styles.dot} aria-hidden="true" />
              <span>thinking…</span>
            </span>
          ) : (
            <>{message.content}</>
          )}
          {message.role === 'assistant' && message.citations.length > 0 ? (
            <div className={styles.citations} aria-label="Citations">
              {message.citations.map((entityId, idx) => (
                <CitationLink
                  key={`${message.id}-${entityId}-${idx}`}
                  entityId={entityId}
                  index={idx}
                />
              ))}
            </div>
          ) : null}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
