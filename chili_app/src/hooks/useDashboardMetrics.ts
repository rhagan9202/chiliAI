import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'
import type {
  AlertListResponse,
  KnowledgeBaseListResponse,
} from '../types/api'
import type { DashboardMetrics } from '../types/dashboard'

export const dashboardMetricsQueryKey = ['dashboard', 'metrics'] as const

async function fetchDashboardMetrics(): Promise<DashboardMetrics> {
  const [kbResponse, alertsResponse] = await Promise.all([
    apiRequest<KnowledgeBaseListResponse>('/knowledgebases'),
    apiRequest<AlertListResponse>('/alerts?status=open&limit=500'),
  ])

  let totalEntities = 0
  let totalRelationships = 0
  let activeKnowledgeBases = 0
  for (const kb of kbResponse.items) {
    totalEntities += kb.entity_count
    totalRelationships += kb.relationship_count
    if (kb.status === 'active' || kb.status === 'ready') {
      activeKnowledgeBases += 1
    }
  }

  return {
    totalEntities,
    totalRelationships,
    openAlerts: alertsResponse.total,
    activeKnowledgeBases,
  }
}

export function useDashboardMetrics(): UseQueryResult<
  DashboardMetrics,
  Error
> {
  return useQuery<DashboardMetrics, Error>({
    queryKey: dashboardMetricsQueryKey,
    queryFn: fetchDashboardMetrics,
  })
}
