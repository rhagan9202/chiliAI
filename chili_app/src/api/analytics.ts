import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type { AnalyticsOverviewResponse, RiskScoreResponse, TimeseriesResponse } from './contracts'

export const analyticsOverviewQueryKey = ['analytics', 'overview'] as const

export function riskScoreQueryKey(entityId: string) {
  return ['analytics', 'risk-score', entityId] as const
}

export function timeseriesQueryKey(entityId: string) {
  return ['analytics', 'timeseries', entityId] as const
}

export function getAnalyticsOverview(): Promise<AnalyticsOverviewResponse> {
  return apiFetch<AnalyticsOverviewResponse>('/analytics/overview')
}

export function getRiskScore(entityId: string): Promise<RiskScoreResponse> {
  return apiFetch<RiskScoreResponse>(`/analytics/risk-scores/${entityId}`)
}

export function getTimeseries(entityId: string): Promise<TimeseriesResponse> {
  return apiFetch<TimeseriesResponse>(`/analytics/timeseries/${entityId}`)
}

export function useAnalyticsOverview() {
  return useQuery({
    queryKey: analyticsOverviewQueryKey,
    queryFn: getAnalyticsOverview,
  })
}

export function useRiskScore(entityId: string | null) {
  return useQuery({
    queryKey: riskScoreQueryKey(entityId ?? 'missing'),
    queryFn: () => getRiskScore(entityId ?? ''),
    enabled: Boolean(entityId),
  })
}

export function useTimeseries(entityId: string | null) {
  return useQuery({
    queryKey: timeseriesQueryKey(entityId ?? 'missing'),
    queryFn: () => getTimeseries(entityId ?? ''),
    enabled: Boolean(entityId),
  })
}