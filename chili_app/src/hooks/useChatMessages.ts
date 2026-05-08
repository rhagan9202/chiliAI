import { useCallback, useRef, useState } from 'react'

import { API_BASE_URL } from '../lib/apiClient'
import type { ChatMessage } from '../stores/chatStore'
import { useChatStore } from '../stores/chatStore'

export interface SendMessageArgs {
  conversationId: string
  kbId: string
  content: string
}

export interface UseChatMessagesResult {
  send: (args: SendMessageArgs) => Promise<void>
  cancel: () => void
  isStreaming: boolean
  lastError: Error | null
}

interface SsePayload {
  token?: string
  done?: boolean
  sources?: string[]
  error?: string
}

function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `id-${Math.random().toString(36).slice(2)}-${Date.now()}`
}

function parseSsePayload(line: string): SsePayload | null {
  if (!line.startsWith('data:')) return null
  const json = line.slice(5).trim()
  if (json.length === 0) return null
  try {
    return JSON.parse(json) as SsePayload
  } catch {
    return null
  }
}

export function useChatMessages(): UseChatMessagesResult {
  const appendMessage = useChatStore((s) => s.appendMessage)
  const appendAssistantToken = useChatStore((s) => s.appendAssistantToken)
  const finalizeAssistantMessage = useChatStore((s) => s.finalizeAssistantMessage)
  const failAssistantMessage = useChatStore((s) => s.failAssistantMessage)

  const [isStreaming, setIsStreaming] = useState<boolean>(false)
  const [lastError, setLastError] = useState<Error | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const cancel = useCallback((): void => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  const send = useCallback(
    async ({ conversationId, kbId, content }: SendMessageArgs): Promise<void> => {
      if (content.trim().length === 0) return

      const userMessage: ChatMessage = {
        id: newId(),
        role: 'user',
        content,
        citations: [],
        pending: false,
        createdAt: Date.now(),
      }
      const assistantId = newId()
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        citations: [],
        pending: true,
        createdAt: Date.now(),
      }
      appendMessage(conversationId, userMessage)
      appendMessage(conversationId, assistantMessage)

      setLastError(null)
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      const url = `${API_BASE_URL}/chat/conversations/${encodeURIComponent(conversationId)}/messages?stream=true`

      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify({ content, kb_id: kbId }),
          signal: controller.signal,
        })

        if (!response.ok || !response.body) {
          throw new Error(`Request failed with status ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let citations: string[] = []
        let done = false

        try {
          while (!done) {
            const { value, done: readerDone } = await reader.read()
            if (readerDone) break
            buffer += decoder.decode(value, { stream: true })

            let separatorIndex = buffer.indexOf('\n\n')
            while (separatorIndex !== -1) {
              const event = buffer.slice(0, separatorIndex)
              buffer = buffer.slice(separatorIndex + 2)
              for (const rawLine of event.split('\n')) {
                const payload = parseSsePayload(rawLine)
                if (!payload) continue
                if (payload.error) {
                  throw new Error(payload.error)
                }
                if (typeof payload.token === 'string' && payload.token.length > 0) {
                  appendAssistantToken(conversationId, assistantId, payload.token)
                }
                if (payload.done === true) {
                  citations = payload.sources ?? []
                  done = true
                }
              }
              separatorIndex = buffer.indexOf('\n\n')
            }
          }
        } finally {
          try {
            reader.releaseLock()
          } catch {
            // reader may already be closed; safe to ignore.
          }
        }

        finalizeAssistantMessage(conversationId, assistantId, citations)
      } catch (err: unknown) {
        const isAbort =
          err instanceof DOMException && err.name === 'AbortError'
        const wrapped =
          err instanceof Error ? err : new Error(String(err))
        if (!isAbort) {
          setLastError(wrapped)
        }
        failAssistantMessage(
          conversationId,
          assistantId,
          isAbort ? 'cancelled' : wrapped.message,
        )
      } finally {
        setIsStreaming(false)
        if (abortRef.current === controller) {
          abortRef.current = null
        }
      }
    },
    [
      appendMessage,
      appendAssistantToken,
      finalizeAssistantMessage,
      failAssistantMessage,
    ],
  )

  return { send, cancel, isStreaming, lastError }
}
