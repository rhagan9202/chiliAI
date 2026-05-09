import { useMutation, useQuery } from '@tanstack/react-query'

import { apiFetch, apiPost } from './client'
import type {
  PolicyBriefCreateRequest,
  PolicyBriefResponse,
  PolicyGapCaseListResponse,
  PolicyGapDetailResponse,
  PolicyGapListResponse,
} from './contracts'

export const policyGapsQueryKey = ['policy', 'gaps'] as const

export function policyGapDetailQueryKey(gapId: string) {
  return ['policy', 'gaps', gapId] as const
}

export function policyGapCasesQueryKey(gapId: string) {
  return ['policy', 'gaps', gapId, 'cases'] as const
}

export function getPolicyGaps(): Promise<PolicyGapListResponse> {
  return apiFetch<PolicyGapListResponse>('/policy/gaps')
}

export function getPolicyGap(gapId: string): Promise<PolicyGapDetailResponse> {
  return apiFetch<PolicyGapDetailResponse>(`/policy/gaps/${gapId}`)
}

export function getPolicyGapCases(gapId: string): Promise<PolicyGapCaseListResponse> {
  return apiFetch<PolicyGapCaseListResponse>(`/policy/gaps/${gapId}/cases`)
}

export function createPolicyBrief(
  payload: PolicyBriefCreateRequest,
): Promise<PolicyBriefResponse> {
  return apiPost<PolicyBriefResponse, PolicyBriefCreateRequest>('/policy/briefs', payload)
}

export function usePolicyGaps() {
  return useQuery({
    queryKey: policyGapsQueryKey,
    queryFn: getPolicyGaps,
  })
}

export function usePolicyGap(gapId: string | null) {
  return useQuery({
    queryKey: policyGapDetailQueryKey(gapId ?? 'missing'),
    queryFn: () => getPolicyGap(gapId ?? ''),
    enabled: Boolean(gapId),
  })
}

export function usePolicyGapCases(gapId: string | null) {
  return useQuery({
    queryKey: policyGapCasesQueryKey(gapId ?? 'missing'),
    queryFn: () => getPolicyGapCases(gapId ?? ''),
    enabled: Boolean(gapId),
  })
}

export function useCreatePolicyBrief() {
  return useMutation({
    mutationFn: createPolicyBrief,
  })
}