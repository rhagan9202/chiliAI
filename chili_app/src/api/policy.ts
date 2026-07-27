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

/**
 * Policy items are filtered server-side, so the query is part of the cache key.
 * `statuses` is sorted into the key so ["open","escalated"] and
 * ["escalated","open"] are one cache entry, not two (UXA-401).
 */
export interface PolicyItemQuery {
  statuses?: string[]
  search?: string
}

export const policyItemsQueryKey = (kb: string | null, query?: PolicyItemQuery) =>
  [
    'policy',
    'items',
    kb,
    [...(query?.statuses ?? [])].sort().join(',') || 'all',
    query?.search ?? '',
  ] as const
export const policyItemQueryKey = (kb: string | null, itemId: string | null) =>
  ['policy', 'items', kb, itemId] as const

export function getPolicyItems(
  kb: string,
  query?: PolicyItemQuery,
): Promise<PolicyItemListResponse> {
  const params = new URLSearchParams({ knowledge_base_id: kb })
  // Repeated `status=` — the API matches any of them.
  for (const status of query?.statuses ?? []) params.append('status', status)
  if (query?.search) params.set('q', query.search)
  return apiFetch<PolicyItemListResponse>(`/policy/items?${params.toString()}`)
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

export function usePolicyItems(kb: string | null, query?: PolicyItemQuery) {
  return useQuery({
    queryKey: policyItemsQueryKey(kb, query),
    queryFn: () => getPolicyItems(kb ?? '', query),
    enabled: Boolean(kb),
    // Typing in the search box re-queries; keeping the previous page on screen
    // stops the queue flashing its loading state on every keystroke.
    placeholderData: (previous) => previous,
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
