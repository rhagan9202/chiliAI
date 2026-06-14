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

export function alertDetailQueryKey(alertId: string) {
  return ['alerts', alertId] as const
}

export function alertListQueryKey(filters: AlertFeedFilters = {}) {
  return ['alerts', filters] as const
}

export function getAlerts(filters: AlertFeedFilters = {}): Promise<AlertListResponse> {
  const searchParams = new URLSearchParams()
  if (filters.knowledgeBaseId) {
    searchParams.set('kb', filters.knowledgeBaseId)
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

export function getAlert(alertId: string): Promise<AlertDetailResponse> {
  return apiFetch<AlertDetailResponse>(`/alerts/${alertId}`)
}

export function acknowledgeAlert(alertId: string): Promise<ApiEnvelope> {
  return apiPost<ApiEnvelope, Record<string, never>>(`/alerts/${alertId}/acknowledge`, {})
}

export function useAlerts(filters: AlertFeedFilters = {}) {
  return useQuery({
    queryKey: alertListQueryKey(filters),
    queryFn: () => getAlerts(filters),
  })
}

export function useAlert(alertId: string | null) {
  return useQuery({
    queryKey: alertDetailQueryKey(alertId ?? 'missing'),
    queryFn: () => getAlert(alertId ?? ''),
    enabled: Boolean(alertId),
  })
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: alertsQueryKey })
    },
  })
}
