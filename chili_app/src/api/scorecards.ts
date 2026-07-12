import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  ScorecardExportFormat,
  ScorecardExportResponse,
  ScorecardRunListResponse,
  ScorecardRunResponse,
  ScorecardRunStatus,
} from './contracts'

export type ScorecardRunsFilters = {
  knowledgeBaseId: string
  templateId?: string
  status?: ScorecardRunStatus
  limit?: number
  offset?: number
}

export const scorecardRunsQueryKey = (filters: ScorecardRunsFilters | null) =>
  ['scorecards', 'runs', filters] as const
export const scorecardRunQueryKey = (knowledgeBaseId: string | null, runId: string | null) =>
  ['scorecards', 'runs', knowledgeBaseId, runId] as const

function scorecardRunsQuery(filters: ScorecardRunsFilters): string {
  const params = new URLSearchParams({ knowledge_base_id: filters.knowledgeBaseId })
  if (filters.templateId !== undefined) params.set('template_id', filters.templateId)
  if (filters.status !== undefined) params.set('status', filters.status)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  if (filters.offset !== undefined) params.set('offset', String(filters.offset))
  return params.toString()
}

// Scorecard generation and template listing have no UI surface anymore (the
// dashboard's Generate button was retired 2026-07-07): runs are created via
// POST /scorecards/runs by the seed tool
// (`make seed-housing SEED_ARGS="--scorecards"`) and the endpoints stay
// covered by the backend router tests. Only run viewing/export bindings
// remain here.

export function getScorecardRuns(
  filters: ScorecardRunsFilters,
): Promise<ScorecardRunListResponse> {
  return apiFetch<ScorecardRunListResponse>(`/scorecards/runs?${scorecardRunsQuery(filters)}`)
}

export function getScorecardRun(
  knowledgeBaseId: string,
  runId: string,
): Promise<ScorecardRunResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<ScorecardRunResponse>(
    `/scorecards/runs/${encodeURIComponent(runId)}?${params}`,
  )
}

export function exportScorecardRun(
  knowledgeBaseId: string,
  runId: string,
  format: ScorecardExportFormat = 'json',
): Promise<ScorecardExportResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId, format })
  return apiFetch<ScorecardExportResponse>(
    `/scorecards/runs/${encodeURIComponent(runId)}/export?${params}`,
  )
}

export function useScorecardRuns(filters: ScorecardRunsFilters | null) {
  return useQuery({
    queryKey: scorecardRunsQueryKey(filters),
    queryFn: () => getScorecardRuns(filters ?? { knowledgeBaseId: '' }),
    enabled: Boolean(filters?.knowledgeBaseId),
  })
}

export function useScorecardRun(knowledgeBaseId: string | null, runId: string | null) {
  return useQuery({
    queryKey: scorecardRunQueryKey(knowledgeBaseId, runId),
    queryFn: () => getScorecardRun(knowledgeBaseId ?? '', runId ?? ''),
    enabled: Boolean(knowledgeBaseId && runId),
  })
}
