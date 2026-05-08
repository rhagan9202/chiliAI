// TanStack Query hook for paginated, filtered alert listing.

import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query'
import type {
  UseMutationResult,
  UseQueryResult,
} from '@tanstack/react-query'

import { apiRequest } from '../lib/apiClient'
import type {
  Alert,
  AlertListResponse,
  AlertSeverity,
  AlertStatus,
} from '../types/api'

export interface AlertFilters {
  severity?: AlertSeverity[]
  status?: AlertStatus | null
  entity_type?: string | null
  start_date?: string | null
  end_date?: string | null
  limit?: number
  offset?: number
}

export const ALERTS_QUERY_KEY_BASE = ['alerts'] as const

export function buildAlertsQueryKey(filters: AlertFilters): readonly unknown[] {
  return [
    ...ALERTS_QUERY_KEY_BASE,
    {
      severity: filters.severity ?? [],
      status: filters.status ?? null,
      entity_type: filters.entity_type ?? null,
      start_date: filters.start_date ?? null,
      end_date: filters.end_date ?? null,
      limit: filters.limit ?? 100,
      offset: filters.offset ?? 0,
    },
  ] as const
}

function buildAlertsPath(filters: AlertFilters): string {
  const params = new URLSearchParams()
  // Backend currently accepts a single severity value; pick the first when
  // a multi-select is provided so the request stays valid. Client-side
  // filtering narrows the rest.
  const severity = filters.severity?.[0]
  if (severity) {
    params.set('severity', severity)
  }
  if (filters.status) {
    params.set('status', filters.status)
  }
  if (filters.entity_type) {
    params.set('entity_type', filters.entity_type)
  }
  params.set('limit', String(filters.limit ?? 100))
  params.set('offset', String(filters.offset ?? 0))
  return `/alerts?${params.toString()}`
}

export function useAlerts(
  filters: AlertFilters,
): UseQueryResult<AlertListResponse, Error> {
  return useQuery<AlertListResponse, Error>({
    queryKey: buildAlertsQueryKey(filters),
    queryFn: () => apiRequest<AlertListResponse>(buildAlertsPath(filters)),
  })
}

interface AlertActionResponse {
  alert: Alert
}

export function useAcknowledgeAlerts(): UseMutationResult<
  Alert[],
  Error,
  string[]
> {
  const queryClient = useQueryClient()
  return useMutation<Alert[], Error, string[]>({
    mutationFn: async (alertIds: string[]) => {
      const responses = await Promise.all(
        alertIds.map((id) =>
          apiRequest<AlertActionResponse>(`/alerts/${id}/acknowledge`, {
            method: 'POST',
          }),
        ),
      )
      return responses.map((response) => response.alert)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY_BASE })
    },
  })
}

export interface DismissAlertsInput {
  alertIds: string[]
  resolvedBy: string
  notes?: string
}

export function useDismissAlerts(): UseMutationResult<
  Alert[],
  Error,
  DismissAlertsInput
> {
  const queryClient = useQueryClient()
  return useMutation<Alert[], Error, DismissAlertsInput>({
    mutationFn: async ({ alertIds, resolvedBy, notes }) => {
      const responses = await Promise.all(
        alertIds.map((id) =>
          apiRequest<AlertActionResponse>(`/alerts/${id}/resolve`, {
            method: 'POST',
            body: { resolved_by: resolvedBy, notes },
          }),
        ),
      )
      return responses.map((response) => response.alert)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY_BASE })
    },
  })
}
