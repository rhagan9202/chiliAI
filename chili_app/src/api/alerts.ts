import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPatch, apiPost } from './client'
import type {
  AlertBulkStatusUpdateResponse,
  AlertDetailResponse,
  AlertListResponse,
  AlertOperationResponse,
  AlertStatus,
} from './contracts'

export const alertsQueryKey = ['alerts'] as const

export type AlertFeedFilters = {
  knowledgeBaseId?: string
  status?: string
  statuses?: string[]
  severities?: string[]
  typologies?: string[]
  createdFrom?: string
  createdTo?: string
  evidence?: string
  freshness?: string
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
  for (const status of filters.statuses ?? []) {
    searchParams.append('status', status)
  }
  for (const severity of filters.severities ?? []) {
    searchParams.append('severity', severity)
  }
  for (const typology of filters.typologies ?? []) {
    searchParams.append('typology', typology)
  }
  if (filters.createdFrom) {
    searchParams.set('from', filters.createdFrom)
  }
  if (filters.createdTo) {
    searchParams.set('to', filters.createdTo)
  }
  if (filters.evidence) {
    searchParams.set('evidence', filters.evidence)
  }
  if (filters.freshness) {
    searchParams.set('freshness', filters.freshness)
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
): Promise<AlertOperationResponse> {
  const params = new URLSearchParams({ knowledge_base_id: knowledgeBaseId })
  return apiPost<AlertOperationResponse, Record<string, never>>(
    `/alerts/${encodeURIComponent(alertId)}/acknowledge?${params}`,
    {},
  )
}

export function assignAlert(
  alertId: string,
  knowledgeBaseId: string,
  assignee: string | null,
): Promise<AlertOperationResponse> {
  return apiPatch<AlertOperationResponse, { knowledge_base_id: string; assignee: string | null }>(
    `/alerts/${encodeURIComponent(alertId)}/assignment`,
    { knowledge_base_id: knowledgeBaseId, assignee },
  )
}

export function updateAlertStatus(
  alertId: string,
  knowledgeBaseId: string,
  status: AlertStatus,
  reason?: string,
): Promise<AlertOperationResponse> {
  return apiPatch<AlertOperationResponse, { knowledge_base_id: string; status: AlertStatus; reason?: string }>(
    `/alerts/${encodeURIComponent(alertId)}/status`,
    { knowledge_base_id: knowledgeBaseId, status, ...(reason ? { reason } : {}) },
  )
}

export function bulkUpdateAlertStatus(
  knowledgeBaseId: string,
  alertIds: string[],
  status: AlertStatus,
  reason?: string,
): Promise<AlertBulkStatusUpdateResponse> {
  return apiPost<AlertBulkStatusUpdateResponse, {
    knowledge_base_id: string
    alert_ids: string[]
    status: AlertStatus
    reason?: string
  }>('/alerts/bulk/status', {
    knowledge_base_id: knowledgeBaseId,
    alert_ids: alertIds,
    status,
    ...(reason ? { reason } : {}),
  })
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

export function useAssignAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      alertId,
      knowledgeBaseId,
      assignee,
    }: {
      alertId: string
      knowledgeBaseId: string
      assignee: string | null
    }) => assignAlert(alertId, knowledgeBaseId, assignee),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: alertsQueryKey })
    },
  })
}

export function useUpdateAlertStatus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      alertId,
      knowledgeBaseId,
      status,
      reason,
    }: {
      alertId: string
      knowledgeBaseId: string
      status: AlertStatus
      reason?: string
    }) => updateAlertStatus(alertId, knowledgeBaseId, status, reason),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: alertsQueryKey })
    },
  })
}

export function useBulkUpdateAlertStatus() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      knowledgeBaseId,
      alertIds,
      status,
      reason,
    }: {
      knowledgeBaseId: string
      alertIds: string[]
      status: AlertStatus
      reason?: string
    }) => bulkUpdateAlertStatus(knowledgeBaseId, alertIds, status, reason),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: alertsQueryKey })
    },
  })
}
