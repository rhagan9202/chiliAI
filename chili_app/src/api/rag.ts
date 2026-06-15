import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  ChatConversationCreateRequest,
  ChatConversationResponse,
  ChatMessageCreateRequest,
} from './contracts'

export function conversationQueryKey(conversationId: string) {
  return ['conversation', conversationId] as const
}

export function getConversation(conversationId: string): Promise<ChatConversationResponse> {
  return apiFetch<ChatConversationResponse>(`/chat/conversations/${conversationId}`)
}

export function createConversation(
  payload: ChatConversationCreateRequest,
): Promise<ChatConversationResponse> {
  return apiPost<ChatConversationResponse, ChatConversationCreateRequest>('/chat/conversations', payload)
}

export function addMessage(
  conversationId: string,
  payload: ChatMessageCreateRequest,
): Promise<ChatConversationResponse> {
  if (!conversationId) {
    return Promise.reject(new Error('Cannot add message without an active conversation.'))
  }

  return apiPost<ChatConversationResponse, ChatMessageCreateRequest>(`/chat/conversations/${conversationId}/messages`, payload)
}

export class StartConversationWithMessageError extends Error {
  createdConversation: ChatConversationResponse
  originalError: unknown

  constructor(createdConversation: ChatConversationResponse, originalError: unknown) {
    super('Conversation was created, but the initial message could not be added.')
    this.name = 'StartConversationWithMessageError'
    this.createdConversation = createdConversation
    this.originalError = originalError
  }
}

export function isStartConversationPartialError(
  error: unknown,
): error is StartConversationWithMessageError {
  return error instanceof StartConversationWithMessageError
}

export async function startConversationWithMessage(payload: {
  knowledge_base_id: string
  title: string
  content: string
  filters: Record<string, string | number | boolean>
}): Promise<ChatConversationResponse> {
  const created = await createConversation({
    knowledge_base_id: payload.knowledge_base_id,
    title: payload.title,
  })

  try {
    return await addMessage(created.id, {
      content: payload.content,
      include_graph_context: true,
      filters: payload.filters,
    })
  } catch (error) {
    throw new StartConversationWithMessageError(created, error)
  }
}

export function useConversation(conversationId: string | null) {
  return useQuery({
    queryKey: conversationQueryKey(conversationId ?? 'missing'),
    queryFn: () => getConversation(conversationId ?? ''),
    enabled: Boolean(conversationId),
  })
}

export function useCreateConversation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createConversation,
    onSuccess: (conversation) => {
      queryClient.setQueryData(conversationQueryKey(conversation.id), conversation)
    },
  })
}

export function useAddMessage(conversationId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: ChatMessageCreateRequest) => addMessage(conversationId ?? '', payload),
    onSuccess: (conversation) => {
      queryClient.setQueryData(conversationQueryKey(conversation.id), conversation)
    },
  })
}

export function useStartConversationWithMessage() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: startConversationWithMessage,
    onError: (error) => {
      if (isStartConversationPartialError(error)) {
        queryClient.setQueryData(
          conversationQueryKey(error.createdConversation.id),
          error.createdConversation,
        )
      }
    },
    onSuccess: (conversation) => {
      queryClient.setQueryData(conversationQueryKey(conversation.id), conversation)
      void queryClient.invalidateQueries({ queryKey: conversationQueryKey(conversation.id) })
    },
  })
}
