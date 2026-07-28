import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './client'
import type {
  AnalyticsOverviewResponse,
  GnnClusterResponse,
  MetricTimeseriesResponse,
  RiskScoreListResponse,
  RiskScoreResponse,
  TimeseriesResponse,
} from './contracts'

export function analyticsOverviewQueryKey(knowledgeBaseId: string | null) {
  return ['analytics', 'overview', knowledgeBaseId] as const
}

export type RiskScoresFilters = {
  knowledgeBaseId: string
  entityType?: string
  limit?: number
}

export type MetricTimeseriesFilters = {
  knowledgeBaseId: string
  metric: string
  start: string
  end: string
}

export function riskScoreQueryKey(knowledgeBaseId: string | null, entityId: string | null) {
  return ['analytics', 'risk-score', knowledgeBaseId, entityId] as const
}

export function riskScoresQueryKey(filters: RiskScoresFilters | null) {
  return ['analytics', 'risk-scores', filters] as const
}

export function timeseriesQueryKey(knowledgeBaseId: string | null, entityId: string | null) {
  return ['analytics', 'timeseries', knowledgeBaseId, entityId] as const
}

export function metricTimeseriesQueryKey(filters: MetricTimeseriesFilters | null) {
  return ['analytics', 'metric-timeseries', filters] as const
}

export function gnnClustersQueryKey(knowledgeBaseId: string | null) {
  return ['analytics', 'gnn-clusters', knowledgeBaseId] as const
}

export function getAnalyticsOverview(
  knowledgeBaseId: string | null,
): Promise<AnalyticsOverviewResponse> {
  // Omitting `kb` keeps the endpoint's workspace-wide behaviour (UXA-408).
  const query = knowledgeBaseId ? `?kb=${encodeURIComponent(knowledgeBaseId)}` : ''
  return apiFetch<AnalyticsOverviewResponse>(`/analytics/overview${query}`)
}

export function getRiskScores(filters: RiskScoresFilters): Promise<RiskScoreListResponse> {
  const params = new URLSearchParams({ knowledge_base_id: filters.knowledgeBaseId })
  if (filters.entityType) params.set('entity_type', filters.entityType)
  if (filters.limit !== undefined) params.set('limit', String(filters.limit))
  return apiFetch<RiskScoreListResponse>(`/analytics/risk-scores?${params}`)
}

export function getRiskScore(knowledgeBaseId: string, entityId: string): Promise<RiskScoreResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<RiskScoreResponse>(`/analytics/risk-scores/${encodeURIComponent(entityId)}?${params}`)
}

export function getMetricTimeseries(
  filters: MetricTimeseriesFilters,
): Promise<MetricTimeseriesResponse> {
  const params = new URLSearchParams({
    knowledge_base_id: filters.knowledgeBaseId,
    metric: filters.metric,
    start: filters.start,
    end: filters.end,
  })
  return apiFetch<MetricTimeseriesResponse>(`/analytics/timeseries?${params}`)
}

export function getTimeseries(knowledgeBaseId: string, entityId: string): Promise<TimeseriesResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<TimeseriesResponse>(`/analytics/timeseries/${encodeURIComponent(entityId)}?${params}`)
}

export function getGnnClusters(knowledgeBaseId: string): Promise<GnnClusterResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<GnnClusterResponse>(`/analytics/gnn/clusters?${params}`)
}

export function useAnalyticsOverview(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: analyticsOverviewQueryKey(knowledgeBaseId),
    queryFn: () => getAnalyticsOverview(knowledgeBaseId),
  })
}

export function useRiskScores(filters: RiskScoresFilters | null) {
  return useQuery({
    queryKey: riskScoresQueryKey(filters),
    queryFn: () => getRiskScores(filters ?? { knowledgeBaseId: '' }),
    enabled: Boolean(filters?.knowledgeBaseId),
  })
}

export function useRiskScore(knowledgeBaseId: string | null, entityId: string | null) {
  return useQuery({
    queryKey: riskScoreQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getRiskScore(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId && entityId),
  })
}

export function useMetricTimeseries(filters: MetricTimeseriesFilters | null) {
  return useQuery({
    queryKey: metricTimeseriesQueryKey(filters),
    queryFn: () => getMetricTimeseries(
      filters ?? { knowledgeBaseId: '', metric: '', start: '', end: '' },
    ),
    enabled: Boolean(filters?.knowledgeBaseId),
  })
}

export function useTimeseries(knowledgeBaseId: string | null, entityId: string | null) {
  return useQuery({
    queryKey: timeseriesQueryKey(knowledgeBaseId, entityId),
    queryFn: () => getTimeseries(knowledgeBaseId ?? '', entityId ?? ''),
    enabled: Boolean(knowledgeBaseId && entityId),
  })
}

export function useGnnClusters(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: gnnClustersQueryKey(knowledgeBaseId),
    queryFn: () => getGnnClusters(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}
