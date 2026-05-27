import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { AnalyticsOverviewResponse, RiskScoreResponse, TimeseriesResponse } from './contracts'

export const analyticsOverviewQueryKey = ['analytics', 'overview'] as const

export function riskScoreQueryKey(knowledgeBaseId: string | null, entityId: string | null) {
  return ['analytics', 'risk-score', knowledgeBaseId, entityId] as const
}

export function timeseriesQueryKey(knowledgeBaseId: string | null, entityId: string | null) {
  return ['analytics', 'timeseries', knowledgeBaseId, entityId] as const
}

export function getAnalyticsOverview(): Promise<AnalyticsOverviewResponse> {
  return apiFetch<AnalyticsOverviewResponse>('/analytics/overview')
}

export function getRiskScore(knowledgeBaseId: string, entityId: string): Promise<RiskScoreResponse> {
  const params = new URLSearchParams({ kb_id: knowledgeBaseId })
  return apiFetch<RiskScoreResponse>(`/analytics/risk-scores/${encodeURIComponent(entityId)}?${params}`)
}

export function getTimeseries(knowledgeBaseId: string, entityId: string): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({ kb_id: knowledgeBaseId })
  return apiFetch<TimeseriesResponse>(`/analytics/timeseries/${encodeURIComponent(entityId)}?${params}`)
}

export function useAnalyticsOverview() {
  return useQuery({
    queryKey: analyticsOverviewQueryKey,
    queryFn: getAnalyticsOverview,
  })
}

export function useRiskScore(knowledgeBaseId: string | null, entityId: string | null) {
  return useQuery({
    queryKey: riskScoreQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getRiskScore(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId && entityId),
  })
}

export function useTimeseries(knowledgeBaseId: string | null, entityId: string | null) {
  return useQuery({
    queryKey: timeseriesQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getTimeseries(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId && entityId),
  })
}
