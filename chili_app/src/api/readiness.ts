import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { KnowledgeBaseReadinessResponse } from './contracts'

export function knowledgeBaseReadinessQueryKey(knowledgeBaseId: string | null) {
  return ['knowledge-bases', knowledgeBaseId ?? 'missing', 'readiness'] as const
}

export function getKnowledgeBaseReadiness(
  knowledgeBaseId: string,
): Promise<KnowledgeBaseReadinessResponse> {
  return apiFetch<KnowledgeBaseReadinessResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/readiness`,
  )
}

export function useKnowledgeBaseReadiness(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: knowledgeBaseReadinessQueryKey(knowledgeBaseId),
    queryFn: () => getKnowledgeBaseReadiness(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}
