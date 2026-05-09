import { beforeEach, describe, expect, it } from 'vitest'

import { useChatStore } from '../chatStore'
import type { ChatMessage } from '../chatStore'

const baseMessage = (overrides: Partial<ChatMessage>): ChatMessage => ({
  id: overrides.id ?? 'm1',
  role: overrides.role ?? 'user',
  content: overrides.content ?? '',
  citations: overrides.citations ?? [],
  pending: overrides.pending ?? false,
  createdAt: overrides.createdAt ?? 0,
})

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.setState({
      conversations: {},
      activeConversationId: null,
    })
  })

  it('appends a message to a fresh conversation', () => {
    useChatStore.getState().appendMessage(
      'c1',
      baseMessage({ id: 'u1', role: 'user', content: 'hi' }),
    )
    const messages = useChatStore.getState().conversations['c1'].messages
    expect(messages).toHaveLength(1)
    expect(messages[0].content).toBe('hi')
  })

  it('appends streamed tokens to an existing assistant message', () => {
    useChatStore.getState().appendMessage(
      'c1',
      baseMessage({
        id: 'a1',
        role: 'assistant',
        pending: true,
      }),
    )
    useChatStore.getState().appendAssistantToken('c1', 'a1', 'Hel')
    useChatStore.getState().appendAssistantToken('c1', 'a1', 'lo')
    const messages = useChatStore.getState().conversations['c1'].messages
    expect(messages[0].content).toBe('Hello')
  })

  it('finalizes assistant messages with citations', () => {
    useChatStore.getState().appendMessage(
      'c1',
      baseMessage({ id: 'a1', role: 'assistant', pending: true }),
    )
    useChatStore.getState().finalizeAssistantMessage('c1', 'a1', ['e1', 'e2'])
    const messages = useChatStore.getState().conversations['c1'].messages
    expect(messages[0].pending).toBe(false)
    expect(messages[0].citations).toEqual(['e1', 'e2'])
  })

  it('marks assistant messages as failed', () => {
    useChatStore.getState().appendMessage(
      'c1',
      baseMessage({ id: 'a1', role: 'assistant', pending: true }),
    )
    useChatStore.getState().failAssistantMessage('c1', 'a1', 'network error')
    const messages = useChatStore.getState().conversations['c1'].messages
    expect(messages[0].pending).toBe(false)
    expect(messages[0].content).toContain('network error')
  })

  it('resets a conversation', () => {
    useChatStore.getState().appendMessage(
      'c1',
      baseMessage({ id: 'u1' }),
    )
    useChatStore.getState().resetConversation('c1')
    expect(useChatStore.getState().conversations['c1'].messages).toEqual([])
  })

  it('tracks the active conversation', () => {
    useChatStore.getState().setActiveConversation('c2')
    expect(useChatStore.getState().activeConversationId).toBe('c2')
    expect(useChatStore.getState().conversations['c2'].messages).toEqual([])
  })
})
