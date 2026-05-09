import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPatch, apiPost } from './client'
import type {
  CaseCreateRequest,
  CaseDetailResponse,
  CaseFeedbackCreateRequest,
  CaseListResponse,
  CaseUpdateRequest,
} from './contracts'

export const casesQueryKey = ['cases'] as const

export function caseDetailQueryKey(caseId: string) {
  return ['cases', caseId] as const
}

export function getCases(): Promise<CaseListResponse> {
  return apiFetch<CaseListResponse>('/cases')
}

export function getCase(caseId: string): Promise<CaseDetailResponse> {
  return apiFetch<CaseDetailResponse>(`/cases/${caseId}`)
}

export function createCase(payload: CaseCreateRequest): Promise<CaseDetailResponse> {
  return apiPost<CaseDetailResponse, CaseCreateRequest>('/cases', payload)
}

export function updateCase(caseId: string, payload: CaseUpdateRequest): Promise<CaseDetailResponse> {
  return apiPatch<CaseDetailResponse, CaseUpdateRequest>(`/cases/${caseId}`, payload)
}

export function addCaseFeedback(caseId: string, payload: CaseFeedbackCreateRequest): Promise<CaseDetailResponse> {
  return apiPost<CaseDetailResponse, CaseFeedbackCreateRequest>(`/cases/${caseId}/feedback`, payload)
}

export function useCases() {
  return useQuery({
    queryKey: casesQueryKey,
    queryFn: getCases,
  })
}

export function useCase(caseId: string | null) {
  return useQuery({
    queryKey: caseDetailQueryKey(caseId ?? 'missing'),
    queryFn: () => getCase(caseId ?? ''),
    enabled: Boolean(caseId),
  })
}

export function useCreateCase() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createCase,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: casesQueryKey })
    },
  })
}

export function useUpdateCase(caseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CaseUpdateRequest) => updateCase(caseId ?? '', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: casesQueryKey })
      if (caseId) {
        void queryClient.invalidateQueries({ queryKey: caseDetailQueryKey(caseId) })
      }
    },
  })
}

export function useAddCaseFeedback(caseId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: CaseFeedbackCreateRequest) => addCaseFeedback(caseId ?? '', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: casesQueryKey })
      if (caseId) {
        void queryClient.invalidateQueries({ queryKey: caseDetailQueryKey(caseId) })
      }
    },
  })
}