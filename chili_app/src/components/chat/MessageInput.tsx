import { useState } from 'react'
import type { KeyboardEvent } from 'react'

import styles from './ChatContainer.module.css'

export interface MessageInputProps {
  disabled: boolean
  onSubmit: (content: string) => void
}

export function MessageInput({
  disabled,
  onSubmit,
}: MessageInputProps): React.ReactElement {
  const [draft, setDraft] = useState<string>('')

  const trimmed = draft.trim()
  const canSend = trimmed.length > 0 && !disabled

  const submit = (): void => {
    if (!canSend) return
    onSubmit(trimmed)
    setDraft('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form
      className={styles.inputRow}
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <textarea
        className={styles.input}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask the knowledge base…"
        disabled={disabled}
        aria-label="Chat message"
        rows={1}
        data-testid="chat-input"
      />
      <button
        type="submit"
        className={styles.send}
        disabled={!canSend}
        data-testid="chat-send"
      >
        Send
      </button>
    </form>
  )
}
