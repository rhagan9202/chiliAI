import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { CanonicalIdentityDetailResponse } from './contracts'

export function identityLinksQueryKey(
  knowledgeBaseId: string | null,
  entityId: string | null,
) {
  return [
    'identity',
    'canonical',
    knowledgeBaseId ?? 'missing',
    entityId ?? 'missing',
  ] as const
}

export function getCanonicalIdentityDetail(
  knowledgeBaseId: string,
  entityId: string,
): Promise<CanonicalIdentityDetailResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<CanonicalIdentityDetailResponse>(
    `/identity/canonical/${encodeURIComponent(entityId)}?${params}`,
  )
}

export function useCanonicalIdentityDetail(
  knowledgeBaseId: string | null,
  entityId: string | null,
) {
  return useQuery({
    queryKey: identityLinksQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getCanonicalIdentityDetail(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId) && Boolean(entityId),
    placeholderData: (prev) => prev,
  })
}
