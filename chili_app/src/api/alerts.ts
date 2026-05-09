import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type { AlertDetailResponse, AlertListResponse, ApiEnvelope } from './contracts'

export const alertsQueryKey = ['alerts'] as const

export function alertDetailQueryKey(alertId: string) {
  return ['alerts', alertId] as const
}

export function getAlerts(): Promise<AlertListResponse> {
  return apiFetch<AlertListResponse>('/alerts')
}

export function getAlert(alertId: string): Promise<AlertDetailResponse> {
  return apiFetch<AlertDetailResponse>(`/alerts/${alertId}`)
}

export function acknowledgeAlert(alertId: string): Promise<ApiEnvelope> {
  return apiPost<ApiEnvelope, Record<string, never>>(`/alerts/${alertId}/acknowledge`, {})
}

export function useAlerts() {
  return useQuery({
    queryKey: alertsQueryKey,
    queryFn: getAlerts,
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