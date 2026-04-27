import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'
import type {
  AlertListResponse,
  KnowledgeBaseListResponse,
} from '../types/api'
import type { ActivityEvent } from '../types/dashboard'

export const recentActivityQueryKey = ['dashboard', 'recent-activity'] as const

const MAX_EVENTS = 10

async function fetchRecentActivity(): Promise<ActivityEvent[]> {
  const [kbResponse, alertsResponse] = await Promise.all([
    apiRequest<KnowledgeBaseListResponse>('/knowledgebases'),
    apiRequest<AlertListResponse>('/alerts?limit=20'),
  ])

  const events: ActivityEvent[] = []

  for (const kb of kbResponse.items) {
    events.push({
      id: `kb-${kb.id}`,
      kind: 'kb_created',
      description: `Knowledge base "${kb.name}" created`,
      timestamp: kb.created_at,
      entityId: kb.id,
      entityType: 'knowledge_base',
    })
  }

  for (const alert of alertsResponse.items) {
    events.push({
      id: `alert-${alert.id}`,
      kind: 'alert_opened',
      description: `Alert: ${alert.title}`,
      timestamp: alert.created_at,
      entityId: alert.entity_id,
      entityType: alert.entity_type,
    })
  }

  events.sort(
    (a, b) =>
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
  )

  return events.slice(0, MAX_EVENTS)
}

export function useRecentActivity(): UseQueryResult<ActivityEvent[], Error> {
  return useQuery<ActivityEvent[], Error>({
    queryKey: recentActivityQueryKey,
    queryFn: fetchRecentActivity,
  })
}
