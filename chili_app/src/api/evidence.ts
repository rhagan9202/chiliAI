import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { EvidencePackResponse } from './contracts'

export function evidencePackQueryKey(evidencePackId: string) {
  return ['evidence-pack', evidencePackId] as const
}

export function getEvidencePack(evidencePackId: string): Promise<EvidencePackResponse> {
  return apiFetch<EvidencePackResponse>(`/evidence-packs/${evidencePackId}`)
}

export function useEvidencePack(evidencePackId: string | null) {
  return useQuery({
    queryKey: evidencePackQueryKey(evidencePackId ?? 'missing'),
    queryFn: () => getEvidencePack(evidencePackId ?? ''),
    enabled: Boolean(evidencePackId),
  })
}