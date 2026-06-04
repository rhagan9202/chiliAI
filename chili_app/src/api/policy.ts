import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  PolicyItemDetailResponse,
  PolicyItemListResponse,
  PolicyTriageRequest,
} from './contracts'

const kbQuery = (kb: string, extra?: Record<string, string>) => {
  const params = new URLSearchParams({ knowledge_base_id: kb, ...(extra ?? {}) })
  return params.toString()
}

export const policyItemsQueryKey = (kb: string | null, status?: string) =>
  ['policy', 'items', kb, status ?? 'all'] as const
export const policyItemQueryKey = (kb: string | null, itemId: string | null) =>
  ['policy', 'items', kb, itemId] as const

export function getPolicyItems(kb: string, status?: string): Promise<PolicyItemListResponse> {
  const query = status ? kbQuery(kb, { status }) : kbQuery(kb)
  return apiFetch<PolicyItemListResponse>(`/policy/items?${query}`)
}

export function getPolicyItem(kb: string, itemId: string): Promise<PolicyItemDetailResponse> {
  return apiFetch<PolicyItemDetailResponse>(`/policy/items/${itemId}?${kbQuery(kb)}`)
}

export function triagePolicyItem(
  kb: string, itemId: string, payload: PolicyTriageRequest,
): Promise<PolicyItemDetailResponse> {
  return apiPost<PolicyItemDetailResponse, PolicyTriageRequest>(
    `/policy/items/${itemId}/triage?${kbQuery(kb)}`, payload,
  )
}

export function usePolicyItems(kb: string | null, status?: string) {
  return useQuery({
    queryKey: policyItemsQueryKey(kb, status),
    queryFn: () => getPolicyItems(kb ?? '', status),
    enabled: Boolean(kb),
  })
}

export function usePolicyItem(kb: string | null, itemId: string | null) {
  return useQuery({
    queryKey: policyItemQueryKey(kb, itemId),
    queryFn: () => getPolicyItem(kb ?? '', itemId ?? ''),
    enabled: Boolean(kb) && Boolean(itemId),
  })
}

export function useTriagePolicyItem(kb: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { itemId: string; payload: PolicyTriageRequest }) =>
      triagePolicyItem(kb ?? '', vars.itemId, vars.payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['policy', 'items', kb] })
    },
  })
}
