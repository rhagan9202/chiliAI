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
  return apiPost<ChatConversationResponse, ChatMessageCreateRequest>(`/chat/conversations/${conversationId}/messages`, payload)
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