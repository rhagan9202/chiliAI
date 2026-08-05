import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { GovernanceReportResponse } from './contracts'

export function governanceReportQueryKey(knowledgeBaseId: string | null) {
  return ['governance-report', knowledgeBaseId ?? 'missing'] as const
}

export function getGovernanceReport(
  knowledgeBaseId: string,
): Promise<GovernanceReportResponse> {
  return apiFetch<GovernanceReportResponse>(
    `/knowledgebases/${encodeURIComponent(knowledgeBaseId)}/governance/report`,
  )
}

export function useGovernanceReport(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: governanceReportQueryKey(knowledgeBaseId),
    queryFn: () => getGovernanceReport(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}
