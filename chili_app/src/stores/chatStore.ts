import { create } from 'zustand'

export type ChatRole = 'user' | 'assistant'

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
  citations: string[]
  pending: boolean
  createdAt: number
}

export interface ChatConversation {
  id: string
  messages: ChatMessage[]
}

export interface ChatState {
  conversations: Record<string, ChatConversation>
  activeConversationId: string | null
  setActiveConversation: (conversationId: string) => void
  appendMessage: (conversationId: string, message: ChatMessage) => void
  appendAssistantToken: (
    conversationId: string,
    messageId: string,
    token: string,
  ) => void
  finalizeAssistantMessage: (
    conversationId: string,
    messageId: string,
    citations: string[],
  ) => void
  failAssistantMessage: (
    conversationId: string,
    messageId: string,
    errorText: string,
  ) => void
  resetConversation: (conversationId: string) => void
}

function ensureConversation(
  conversations: Record<string, ChatConversation>,
  conversationId: string,
): ChatConversation {
  const existing = conversations[conversationId]
  if (existing) return existing
  return { id: conversationId, messages: [] }
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: {},
  activeConversationId: null,
  setActiveConversation: (conversationId) =>
    set((state) => ({
      activeConversationId: conversationId,
      conversations: {
        ...state.conversations,
        [conversationId]: ensureConversation(state.conversations, conversationId),
      },
    })),
  appendMessage: (conversationId, message) =>
    set((state) => {
      const convo = ensureConversation(state.conversations, conversationId)
      return {
        conversations: {
          ...state.conversations,
          [conversationId]: {
            ...convo,
            messages: [...convo.messages, message],
          },
        },
      }
    }),
  appendAssistantToken: (conversationId, messageId, token) =>
    set((state) => {
      const convo = state.conversations[conversationId]
      if (!convo) return state
      const messages = convo.messages.map((m) =>
        m.id === messageId ? { ...m, content: m.content + token } : m,
      )
      return {
        conversations: {
          ...state.conversations,
          [conversationId]: { ...convo, messages },
        },
      }
    }),
  finalizeAssistantMessage: (conversationId, messageId, citations) =>
    set((state) => {
      const convo = state.conversations[conversationId]
      if (!convo) return state
      const messages = convo.messages.map((m) =>
        m.id === messageId ? { ...m, citations, pending: false } : m,
      )
      return {
        conversations: {
          ...state.conversations,
          [conversationId]: { ...convo, messages },
        },
      }
    }),
  failAssistantMessage: (conversationId, messageId, errorText) =>
    set((state) => {
      const convo = state.conversations[conversationId]
      if (!convo) return state
      const messages = convo.messages.map((m) =>
        m.id === messageId
          ? {
              ...m,
              pending: false,
              content:
                m.content.length > 0
                  ? `${m.content}\n\n[error: ${errorText}]`
                  : `[error: ${errorText}]`,
            }
          : m,
      )
      return {
        conversations: {
          ...state.conversations,
          [conversationId]: { ...convo, messages },
        },
      }
    }),
  resetConversation: (conversationId) =>
    set((state) => ({
      conversations: {
        ...state.conversations,
        [conversationId]: { id: conversationId, messages: [] },
      },
    })),
}))
