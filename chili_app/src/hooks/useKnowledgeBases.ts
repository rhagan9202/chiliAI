import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  UseMutationResult,
  UseQueryResult,
} from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'
import type {
  CreateKnowledgeBaseRequest,
  KnowledgeBase,
  KnowledgeBaseListResponse,
} from '../types/api'

export type { KnowledgeBase, KnowledgeBaseListResponse } from '../types/api'

export const knowledgeBasesQueryKey = ['knowledge-bases', 'list'] as const

export function knowledgeBaseDetailQueryKey(kbId: string): readonly unknown[] {
  return ['knowledge-bases', 'detail', kbId] as const
}

export function useKnowledgeBases(): UseQueryResult<
  KnowledgeBaseListResponse,
  Error
> {
  return useQuery<KnowledgeBaseListResponse, Error>({
    queryKey: knowledgeBasesQueryKey,
    queryFn: () =>
      apiRequest<KnowledgeBaseListResponse>('/knowledgebases'),
  })
}

export function useKnowledgeBase(
  kbId: string | undefined,
): UseQueryResult<KnowledgeBase, Error> {
  return useQuery<KnowledgeBase, Error>({
    queryKey: kbId
      ? knowledgeBaseDetailQueryKey(kbId)
      : ['knowledge-bases', 'detail', 'idle'],
    queryFn: () => apiRequest<KnowledgeBase>(`/knowledgebases/${kbId ?? ''}`),
    enabled: Boolean(kbId),
  })
}

export function useCreateKnowledgeBase(): UseMutationResult<
  KnowledgeBase,
  Error,
  CreateKnowledgeBaseRequest
> {
  const queryClient = useQueryClient()
  return useMutation<KnowledgeBase, Error, CreateKnowledgeBaseRequest>({
    mutationFn: (payload) =>
      apiRequest<KnowledgeBase>('/knowledgebases', {
        method: 'POST',
        body: payload,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: knowledgeBasesQueryKey })
    },
  })
}
