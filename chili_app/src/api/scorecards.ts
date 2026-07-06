import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  ScorecardExportFormat,
  ScorecardExportResponse,
  ScorecardRunGenerateRequest,
  ScorecardRunListResponse,
  ScorecardRunResponse,
  ScorecardRunStatus,
  ScorecardTemplateListResponse,
} from './contracts'

export type ScorecardRunsFilters = {
  knowledgeBaseId: string
  templateId?: string
  status?: ScorecardRunStatus
  limit?: number
  offset?: number
}

export const scorecardTemplatesQueryKey = () => ['scorecards', 'templates'] as const
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

export function getScorecardTemplates(): Promise<ScorecardTemplateListResponse> {
  return apiFetch<ScorecardTemplateListResponse>('/scorecards/templates')
}

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

export function generateScorecardRun(
  payload: ScorecardRunGenerateRequest,
): Promise<ScorecardRunResponse> {
  return apiPost<ScorecardRunResponse, ScorecardRunGenerateRequest>('/scorecards/runs', payload)
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

export function useScorecardTemplates() {
  return useQuery({
    queryKey: scorecardTemplatesQueryKey(),
    queryFn: getScorecardTemplates,
  })
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

export function useGenerateScorecardRun() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: generateScorecardRun,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['scorecards'] })
      void queryClient.invalidateQueries({ queryKey: ['housing'] })
    },
  })
}
