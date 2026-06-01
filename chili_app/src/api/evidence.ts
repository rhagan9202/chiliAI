import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { EvidencePackResponse } from './contracts'

export function evidencePackQueryKey(evidencePackId: string, knowledgeBaseId: string) {
  return ['evidence-pack', knowledgeBaseId, evidencePackId] as const
}

export function getEvidencePack(
  evidencePackId: string,
  knowledgeBaseId: string,
): Promise<EvidencePackResponse> {
  const query = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<EvidencePackResponse>(
    `/evidence-packs/${encodeURIComponent(evidencePackId)}?${query.toString()}`,
  )
}

export function useEvidencePack(
  evidencePackId: string | null,
  knowledgeBaseId: string | null,
) {
  return useQuery({
    queryKey: evidencePackQueryKey(evidencePackId ?? 'missing', knowledgeBaseId ?? 'missing'),
    queryFn: () => getEvidencePack(evidencePackId ?? '', knowledgeBaseId ?? ''),
    enabled: Boolean(evidencePackId) && Boolean(knowledgeBaseId),
  })
}
