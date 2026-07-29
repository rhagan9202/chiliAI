import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type { AlertDetailResponse, AlertListResponse, ApiEnvelope } from './contracts'

export const alertsQueryKey = ['alerts'] as const

export type AlertFeedFilters = {
  knowledgeBaseId?: string
  status?: string
  limit?: number
  offset?: number
}

export function alertDetailQueryKey(alertId: string, knowledgeBaseId: string) {
  return ['alerts', knowledgeBaseId, alertId] as const
}

export function alertListQueryKey(filters: AlertFeedFilters = {}) {
  return ['alerts', filters] as const
}

export function getAlerts(filters: AlertFeedFilters = {}): Promise<AlertListResponse> {
  const searchParams = new URLSearchParams()
  if (filters.knowledgeBaseId) {
    searchParams.set('knowledge_base_id', filters.knowledgeBaseId)
  }
  if (filters.status) {
    searchParams.set('status', filters.status)
  }
  if (filters.limit !== undefined) {
    searchParams.set('limit', String(filters.limit))
  }
  if (filters.offset !== undefined) {
    searchParams.set('offset', String(filters.offset))
  }
  const queryString = searchParams.toString()
  return apiFetch<AlertListResponse>(queryString ? `/alerts?${queryString}` : '/alerts')
}

// The alert routes are KB-scoped: an alert id alone used to read and mutate
// any knowledge base's alert, so both now carry the owning KB and 404 without
// it. Callers take the id from the alert record itself rather than the page's
// URL, which may not carry one.
export function getAlert(alertId: string, knowledgeBaseId: string): Promise<AlertDetailResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiFetch<AlertDetailResponse>(`/alerts/${encodeURIComponent(alertId)}?${params}`)
}

export function acknowledgeAlert(
  alertId: string,
  knowledgeBaseId: string,
): Promise<ApiEnvelope> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiPost<ApiEnvelope, Record<string, never>>(
    `/alerts/${encodeURIComponent(alertId)}/acknowledge?${params}`,
    {},
  )
}

export function useAlerts(filters: AlertFeedFilters = {}) {
  return useQuery({
    queryKey: alertListQueryKey(filters),
    queryFn: () => getAlerts(filters),
  })
}

export function useAlert(alertId: string | null, knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: alertDetailQueryKey(alertId ?? 'missing', knowledgeBaseId ?? 'missing'),
    queryFn: () => getAlert(alertId ?? '', knowledgeBaseId ?? ''),
    enabled: Boolean(alertId) && Boolean(knowledgeBaseId),
  })
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      alertId,
      knowledgeBaseId,
    }: {
      alertId: string
      knowledgeBaseId: string
    }) => acknowledgeAlert(alertId, knowledgeBaseId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: alertsQueryKey })
    },
  })
}
