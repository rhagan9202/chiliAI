import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  EvidenceExportFormat,
  EvidencePackExportResponse,
  EvidencePackResponse,
} from './contracts'

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

/**
 * Fetch a downloadable rendering of one evidence pack (UXA-405).
 *
 * Not a query: an export is an action with a side effect (a file lands on
 * disk), so it must not be cached, refetched or deduped.
 */
export function exportEvidencePack(
  evidencePackId: string,
  knowledgeBaseId: string,
  format: EvidenceExportFormat,
): Promise<EvidencePackExportResponse> {
  const query = new URLSearchParams({ knowledge_base_id: knowledgeBaseId, format })
  return apiFetch<EvidencePackExportResponse>(
    `/evidence-packs/${encodeURIComponent(evidencePackId)}/export?${query.toString()}`,
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
