import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  ChatConversationCreateRequest,
  ChatConversationListResponse,
  ChatConversationResponse,
  ChatMessageCreateRequest,
} from './contracts'

export function conversationListQueryKey(knowledgeBaseId: string | null) {
  return ['rag', 'conversations', knowledgeBaseId] as const
}

export function getConversations(
  knowledgeBaseId: string,
): Promise<ChatConversationListResponse> {
  return apiFetch<ChatConversationListResponse>(
    `/chat/conversations?kb=${encodeURIComponent(knowledgeBaseId)}`,
  )
}

export function conversationQueryKey(conversationId: string, knowledgeBaseId: string) {
  return ['conversation', knowledgeBaseId, conversationId] as const
}

// Conversation reads and appends are KB-scoped: a transcript used to be
// readable, and retrieval drivable, by id alone from outside the owning
// knowledge base.
export function getConversation(
  conversationId: string,
  knowledgeBaseId: string,
): Promise<ChatConversationResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<ChatConversationResponse>(
    `/chat/conversations/${encodeURIComponent(conversationId)}?${params}`,
  )
}

export function createConversation(
  payload: ChatConversationCreateRequest,
): Promise<ChatConversationResponse> {
  return apiPost<ChatConversationResponse, ChatConversationCreateRequest>('/chat/conversations', payload)
}

export function addMessage(
  conversationId: string,
  knowledgeBaseId: string,
  payload: ChatMessageCreateRequest,
): Promise<ChatConversationResponse> {
  if (!conversationId) {
    return Promise.reject(new Error('Cannot add message without an active conversation.'))
  }

  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiPost<ChatConversationResponse, ChatMessageCreateRequest>(
    `/chat/conversations/${encodeURIComponent(conversationId)}/messages?${params}`,
    payload,
  )
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
    return await addMessage(created.id, payload.knowledge_base_id, {
      content: payload.content,
      include_graph_context: true,
      filters: payload.filters,
    })
  } catch (error) {
    throw new StartConversationWithMessageError(created, error)
  }
}

/** The active KB's conversations, so a past one can be resumed (UXA-403). */
export function useConversations(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: conversationListQueryKey(knowledgeBaseId),
    queryFn: () => getConversations(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}

export function useConversation(
  conversationId: string | null,
  knowledgeBaseId: string | null,
) {
  return useQuery({
    queryKey: conversationQueryKey(conversationId ?? 'missing', knowledgeBaseId ?? 'missing'),
    queryFn: () => getConversation(conversationId ?? '', knowledgeBaseId ?? ''),
    enabled: Boolean(conversationId) && Boolean(knowledgeBaseId),
  })
}

export function useCreateConversation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createConversation,
    onSuccess: (conversation) => {
      queryClient.setQueryData(
        conversationQueryKey(conversation.id, conversation.knowledge_base_id),
        conversation,
      )
    },
  })
}

export function useAddMessage(
  conversationId: string | null,
  knowledgeBaseId: string | null,
) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: ChatMessageCreateRequest) =>
      addMessage(conversationId ?? '', knowledgeBaseId ?? '', payload),
    onSuccess: (conversation) => {
      queryClient.setQueryData(
        conversationQueryKey(conversation.id, conversation.knowledge_base_id),
        conversation,
      )
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
          conversationQueryKey(
            error.createdConversation.id,
            error.createdConversation.knowledge_base_id,
          ),
          error.createdConversation,
        )
      }
    },
    onSuccess: (conversation) => {
      const key = conversationQueryKey(conversation.id, conversation.knowledge_base_id)
      queryClient.setQueryData(key, conversation)
      void queryClient.invalidateQueries({ queryKey: key })
    },
  })
}
