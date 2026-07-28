import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiFetch, apiPatch, apiPost } from './client'
import type {
  CaseAttachAlertRequest,
  CaseCreateRequest,
  CaseDetailResponse,
  CaseFeedbackCreateRequest,
  CaseListResponse,
  CasePromoteRequest,
  CaseUpdateRequest,
} from './contracts'

function kbQuery(knowledgeBaseId: string): string {
  return new URLSearchParams({ knowledge_base_id: knowledgeBaseId }).toString()
}

export function casesQueryKey(knowledgeBaseId: string) {
  return ['cases', knowledgeBaseId] as const
}

export function caseDetailQueryKey(knowledgeBaseId: string, caseId: string) {
  return ['cases', knowledgeBaseId, caseId] as const
}

export function getCases(knowledgeBaseId: string): Promise<CaseListResponse> {
  return apiFetch<CaseListResponse>(`/cases?${kbQuery(knowledgeBaseId)}`)
}

export function getCase(knowledgeBaseId: string, caseId: string): Promise<CaseDetailResponse> {
  return apiFetch<CaseDetailResponse>(
    `/cases/${encodeURIComponent(caseId)}?${kbQuery(knowledgeBaseId)}`,
  )
}

export function createCase(
  knowledgeBaseId: string,
  payload: CaseCreateRequest,
): Promise<CaseDetailResponse> {
  return apiPost<CaseDetailResponse, CaseCreateRequest>(
    `/cases?${kbQuery(knowledgeBaseId)}`,
    payload,
  )
}

export function updateCase(
  knowledgeBaseId: string,
  caseId: string,
  payload: CaseUpdateRequest,
): Promise<CaseDetailResponse> {
  return apiPatch<CaseDetailResponse, CaseUpdateRequest>(
    `/cases/${encodeURIComponent(caseId)}?${kbQuery(knowledgeBaseId)}`,
    payload,
  )
}

export function addCaseFeedback(
  knowledgeBaseId: string,
  caseId: string,
  payload: CaseFeedbackCreateRequest,
): Promise<CaseDetailResponse> {
  return apiPost<CaseDetailResponse, CaseFeedbackCreateRequest>(
    `/cases/${encodeURIComponent(caseId)}/feedback?${kbQuery(knowledgeBaseId)}`,
    payload,
  )
}

export function promoteCase(
  knowledgeBaseId: string,
  payload: CasePromoteRequest,
): Promise<CaseDetailResponse> {
  return apiPost<CaseDetailResponse, CasePromoteRequest>(
    `/cases/promote?${kbQuery(knowledgeBaseId)}`,
    payload,
  )
}

/**
 * Add an alert to a case that already exists (UXA-405).
 *
 * The other half of `promoteCase`: promote opens a *new* case, this adds to one
 * an analyst already has open.
 */
export function attachAlertToCase(
  knowledgeBaseId: string,
  caseId: string,
  payload: CaseAttachAlertRequest,
): Promise<CaseDetailResponse> {
  return apiPost<CaseDetailResponse, CaseAttachAlertRequest>(
    `/cases/${encodeURIComponent(caseId)}/alerts?${kbQuery(knowledgeBaseId)}`,
    payload,
  )
}

export type PromoteAlertToCaseInput = {
  knowledgeBaseId: string
  alertId: string
  notes?: string
}

export function promoteAlertToCase({
  knowledgeBaseId,
  alertId,
  notes,
}: PromoteAlertToCaseInput): Promise<CaseDetailResponse> {
  return promoteCase(knowledgeBaseId, { alert_id: alertId, notes })
}

export function useCases(knowledgeBaseId: string | null) {
  return useQuery({
    queryKey: casesQueryKey(knowledgeBaseId ?? 'missing'),
    queryFn: () => getCases(knowledgeBaseId ?? ''),
    enabled: Boolean(knowledgeBaseId),
  })
}

export function useCase(knowledgeBaseId: string | null, caseId: string | null) {
  return useQuery({
    queryKey: caseDetailQueryKey(knowledgeBaseId ?? 'missing', caseId ?? 'missing'),
    queryFn: () => getCase(knowledgeBaseId ?? '', caseId ?? ''),
    enabled: Boolean(knowledgeBaseId) && Boolean(caseId),
  })
}

function useCaseInvalidation(knowledgeBaseId: string | null, caseId: string | null) {
  const queryClient = useQueryClient()
  return () => {
    void queryClient.invalidateQueries({ queryKey: casesQueryKey(knowledgeBaseId ?? 'missing') })
    if (knowledgeBaseId && caseId) {
      void queryClient.invalidateQueries({
        queryKey: caseDetailQueryKey(knowledgeBaseId, caseId),
      })
    }
  }
}

export function useCreateCase(knowledgeBaseId: string | null) {
  const invalidate = useCaseInvalidation(knowledgeBaseId, null)
  return useMutation({
    mutationFn: (payload: CaseCreateRequest) => createCase(knowledgeBaseId ?? '', payload),
    onSuccess: invalidate,
  })
}

export function useUpdateCase(knowledgeBaseId: string | null, caseId: string | null) {
  const invalidate = useCaseInvalidation(knowledgeBaseId, caseId)
  return useMutation({
    mutationFn: (payload: CaseUpdateRequest) =>
      updateCase(knowledgeBaseId ?? '', caseId ?? '', payload),
    onSuccess: invalidate,
  })
}

export function useAddCaseFeedback(knowledgeBaseId: string | null, caseId: string | null) {
  const invalidate = useCaseInvalidation(knowledgeBaseId, caseId)
  return useMutation({
    mutationFn: (payload: CaseFeedbackCreateRequest) =>
      addCaseFeedback(knowledgeBaseId ?? '', caseId ?? '', payload),
    onSuccess: invalidate,
  })
}

export function usePromoteCase(knowledgeBaseId: string | null) {
  const invalidate = useCaseInvalidation(knowledgeBaseId, null)
  return useMutation({
    mutationFn: (payload: CasePromoteRequest) => promoteCase(knowledgeBaseId ?? '', payload),
    onSuccess: invalidate,
  })
}

export function useAttachAlertToCase(knowledgeBaseId: string | null) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (vars: { caseId: string; payload: CaseAttachAlertRequest }) =>
      attachAlertToCase(knowledgeBaseId ?? '', vars.caseId, vars.payload),
    onSuccess: (_detail, vars) => {
      void queryClient.invalidateQueries({
        queryKey: casesQueryKey(knowledgeBaseId ?? 'missing'),
      })
      if (knowledgeBaseId) {
        void queryClient.invalidateQueries({
          queryKey: caseDetailQueryKey(knowledgeBaseId, vars.caseId),
        })
      }
    },
  })
}

export function usePromoteAlertToCase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: promoteAlertToCase,
    onSuccess: (_detail, variables) => {
      void queryClient.invalidateQueries({ queryKey: casesQueryKey(variables.knowledgeBaseId) })
    },
  })
}
